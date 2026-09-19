from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

BLOCKER_RE = re.compile(r"captcha|recaptcha|hcaptcha|verification code|two[- ]factor|\bmfa\b", re.I)
APPLY_RE = re.compile(r"\b(apply|apply now|apply for this job|start application|continue application)\b", re.I)
FINAL_RE = re.compile(r"\b(submit application|submit|send application|complete application)\b", re.I)


def provider_from_url(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    for token, name in (
        ("greenhouse", "greenhouse"), ("lever", "lever"), ("ashby", "ashby"),
        ("myworkdayjobs", "workday"), ("smartrecruiters", "smartrecruiters"),
        ("icims", "icims"), ("jobvite", "jobvite"), ("dice.com", "dice"),
    ):
        if token in host:
            return name
    return "generic"


def _text(scope) -> str:
    try:
        return scope.locator("body").inner_text(timeout=5000)
    except Exception:
        try:
            return scope.locator("html").inner_text(timeout=3000)
        except Exception:
            return ""


def _interactive_count(scope) -> int:
    try:
        return scope.locator('input:not([type="hidden"]), textarea, select, [role="combobox"]').count()
    except Exception:
        return 0


def wait_for_render(page, timeout_ms=20000):
    """Wait for client-rendered ATS content without assuming network-idle."""
    elapsed = 0
    best = {"body": "", "controls": 0}
    while elapsed <= timeout_ms:
        body = _text(page)
        controls = _interactive_count(page)
        if len(body) > len(best["body"]):
            best = {"body": body, "controls": controls}
        if len(body.strip()) >= 80 or controls:
            page.wait_for_timeout(1000)
            return {"body": _text(page) or body, "controls": _interactive_count(page)}
        page.wait_for_timeout(500)
        elapsed += 500
    return best


def scopes(page):
    """Return main page plus accessible child frames."""
    out = [page]
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            _ = frame.url
            out.append(frame)
        except Exception:
            pass
    return out


def _blocker_details(page):
    found = []
    for scope in scopes(page):
        url = getattr(scope, "url", "") or ""
        text = _text(scope)
        haystack = f"{url} {text}"
        if BLOCKER_RE.search(haystack) or "hcaptcha.com" in url or "recaptcha" in url.lower():
            found.append({"url": url, "excerpt": re.sub(r"\\s+", " ", text).strip()[:300]})
    return found


def analyze(page):
    rendered = wait_for_render(page)
    body = rendered["body"]
    frames = []
    for scope in scopes(page):
        text = _text(scope)
        frames.append({
            "url": getattr(scope, "url", page.url),
            "body_length": len(text),
            "controls": _interactive_count(scope),
        })
    blocker_details = _blocker_details(page)
    return {
        "url": page.url,
        "provider": provider_from_url(page.url),
        "body_length": len(body),
        "body_excerpt": re.sub(r"\s+", " ", body).strip()[:2500],
        "controls": sum(x["controls"] for x in frames),
        "frames": frames,
        "blocker_detected": bool(BLOCKER_RE.search(body) or blocker_details),
        "blocker_details": blocker_details,
    }


def _apply_candidates(scope):
    rows = []
    loc = scope.locator("a, button, [role=button], input[type=button], input[type=submit]")
    for i in range(min(loc.count(), 300)):
        el = loc.nth(i)
        try:
            if not el.is_visible():
                continue
            text = (el.inner_text(timeout=800) or el.get_attribute("value") or el.get_attribute("aria-label") or "").strip()
            if not APPLY_RE.search(text) or FINAL_RE.search(text):
                continue
            rows.append((text, el.get_attribute("href"), el))
        except Exception:
            pass
    return rows


def enter_application(page, provider=None, timeout_ms=20000):
    """Reach an application form safely. Never clicks a final-submit action."""
    provider = (provider or provider_from_url(page.url)).lower()
    diag = {"provider": provider, "start_url": page.url, "attempts": [], "entered": False}
    rendered = wait_for_render(page, timeout_ms)
    body = rendered["body"]
    initial_blockers = _blocker_details(page)
    if BLOCKER_RE.search(body) or initial_blockers:
        diag["blocker"] = "CAPTCHA/MFA/verification challenge detected"
        diag["blocker_details"] = initial_blockers
        return diag

    if rendered["controls"] > 0 and page.locator('input[type="file"]').count() > 0:
        diag["entered"] = True
        diag["method"] = "form_already_visible"
        diag["final_url"] = page.url
        return diag

    for scope in scopes(page):
        for text, href, el in _apply_candidates(scope):
            attempt = {"text": text, "href": href, "scope_url": getattr(scope, "url", page.url)}
            diag["attempts"].append(attempt)
            try:
                if href:
                    destination = urljoin(getattr(scope, "url", page.url), href)
                    page.goto(destination, wait_until="domcontentloaded", timeout=60000)
                    attempt["method"] = "href_navigation"
                else:
                    # Apply is an entry action, but never click anything whose text
                    # resembles final submission.
                    if FINAL_RE.search(text):
                        continue
                    before = page.url
                    el.click(timeout=7000)
                    attempt["method"] = "controlled_apply_click"
                    attempt["url_before"] = before
                wait_for_render(page, timeout_ms)
                after = analyze(page)
                attempt["after"] = after
                if after["blocker_detected"]:
                    diag["blocker"] = "CAPTCHA/MFA/verification challenge detected"
                    diag["blocker_details"] = after.get("blocker_details", [])
                    diag["final_url"] = page.url
                    return diag
                if after["controls"] > 0 or page.url != diag["start_url"]:
                    diag["entered"] = True
                    diag["method"] = attempt["method"]
                    diag["entry_text"] = text
                    diag["final_url"] = page.url
                    return diag
            except Exception as exc:
                attempt["error"] = str(exc)

    # iCIMS and similar sites can put the actual experience inside an iframe.
    for scope in scopes(page):
        if scope is page:
            continue
        if _interactive_count(scope) > 0:
            diag["entered"] = True
            diag["method"] = "embedded_form"
            diag["form_frame_url"] = scope.url
            diag["final_url"] = page.url
            return diag

    diag["final_url"] = page.url
    diag["reason"] = "No safe application entry or rendered form was found."
    return diag


def form_scope(page):
    """Pick the page/frame containing the largest visible application form."""
    ranked = sorted(scopes(page), key=_interactive_count, reverse=True)
    return ranked[0] if ranked else page
