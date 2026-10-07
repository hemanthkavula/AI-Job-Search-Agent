from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import os
import re
import shutil
import threading
try:
    import fcntl
except ImportError:  # pragma: no cover - Windows/local fallback
    fcntl = None
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app import batch_prepare
from app.ats_resolver import resolve_original_ats
from app.jd_finalizer import (
    _best_resolved_description,
    _clean_html,
    _fetch_public_page,
    _jsonld_jobpostings,
    _looks_like_complete_jd,
    _looks_like_usable_jd,
    resolve_full_jd,
)
from app.source_registry import detect_ats

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path(os.getenv("JOB_AGENT_STATE_DIR", ROOT / "generated"))
MANUAL_DIR = STATE_DIR / "manual_job_links"
STATE_FILE = MANUAL_DIR / "manual_jobs.json"
WORK_DIR = MANUAL_DIR / "work"
ARTIFACT_DIR = MANUAL_DIR / "resumes"
router = APIRouter()
_STATE_LOCK = threading.RLock()
_PREPARE_LOCK = threading.Lock()
_BATCH_LOCK = threading.Lock()

_PROCESSING_STATUSES = {"PENDING", "JD_READY", "FETCHING_JD", "GENERATING_RESUME"}
_PROVIDER_LABELS = {
    "workday": "Workday", "greenhouse": "Greenhouse", "lever": "Lever",
    "ashby": "Ashby", "smartrecruiters": "SmartRecruiters", "icims": "iCIMS",
    "jobvite": "Jobvite", "dayforce": "Dayforce", "oracle": "Oracle",
    "successfactors": "SuccessFactors", "ultipro": "UKG / UltiPro",
    "ultipro_ukg": "UKG / UltiPro", "ukg": "UKG", "radancy": "Radancy",
    "career_site": "Employer career site",
}
_ATS_VENDOR_NAMES = {
    "workday", "myworkdayjobs", "greenhouse", "lever", "ashby", "smartrecruiters",
    "icims", "jobvite", "dayforce", "dayforcehcm", "oracle", "oraclecloud",
    "successfactors", "ultipro", "ukg", "radancy",
}
_AGGREGATOR_NAMES = {
    "adzuna", "dice", "indeed", "linkedin", "ziprecruiter", "monster",
    "wellfound", "built in", "builtin", "yc jobs", "y combinator",
    "glassdoor", "simplyhired", "careerbuilder",
}
_AGGREGATOR_HOSTS = (
    "adzuna.com", "dice.com", "indeed.com", "linkedin.com", "ziprecruiter.com",
    "monster.com", "wellfound.com", "builtin.com", "ycombinator.com",
    "glassdoor.com", "simplyhired.com", "careerbuilder.com",
)
_GENERIC_JOB_TITLES = {
    "job", "job details", "job detail", "job search", "jobs", "careers",
    "career", "recruitment", "career opportunities", "job opening",
    "finance, service, engineering, & developer jobs",
}


def _collapse_label(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip(" |–—-\t\r\n")


def _slug_label(value: str | None) -> str:
    raw = _collapse_label(value)
    if not raw:
        return ""
    raw = raw.split("|", 1)[0]
    raw = raw.split(".", 1)[0]
    raw = re.sub(r"[_-]+", " ", raw).strip()
    if not raw or len(raw) > 64 or re.fullmatch(r"[0-9a-fA-F-]{16,}", raw):
        return ""
    return raw if any(ch.isupper() for ch in raw[1:]) else raw.title()


def _clean_company_label(value: str | None) -> str:
    label = _collapse_label(value)
    if not label:
        return ""
    label = re.sub(
        r"(?i)\s+(?:global\s+career\s+site|career\s+site|careers|jobs)\s*$",
        "",
        label,
    ).strip()
    low = label.lower().strip()
    if not label or low in {"unknown company", "company", "job search", "job details"}:
        return ""
    if low in _ATS_VENDOR_NAMES or low in _AGGREGATOR_NAMES:
        return ""
    if any(low == name or low.startswith(name + " ") for name in _AGGREGATOR_NAMES):
        return ""
    return label[:180]


def _company_compare_key(value: str | None) -> str:
    clean = _clean_company_label(value)
    if not clean:
        return ""
    low = clean.lower()
    low = re.sub(r"\b(?:incorporated|inc|corp(?:oration)?|llc|ltd|limited|plc|company|co)\b\.?$", "", low).strip()
    return re.sub(r"[^a-z0-9]+", "", low)


def _verified_company(
    *,
    resolved_meta: dict,
    initial_meta: dict,
    provider: str | None,
    identifier: str | None,
    effective_url: str,
    submitted_url: str,
    raw_company: str | None,
    resolved_site_name: str | None,
    resolved_fallback: str | None,
    initial_site_name: str | None,
    initial_fallback: str | None,
) -> tuple[str, str]:
    """Return a company only when its source is strong or independently corroborated."""
    for value, source in (
        (resolved_meta.get("company"), "resolved_jobposting"),
        (initial_meta.get("company"), "submitted_jobposting"),
    ):
        clean = _clean_company_label(value)
        if clean:
            return clean, source

    ats_hint = _ats_company_hint(provider, identifier, effective_url)
    if ats_hint:
        return ats_hint, "ats_tenant"

    # A direct domain is only a hint; never accept it by itself. Require
    # corroboration from independent page metadata to avoid treating a vendor,
    # staffing portal, or white-label career site as the employer.
    direct_hint = _ats_company_hint(None, None, effective_url)

    # Portal/page-title/domain values are accepted only when two independent
    # signals agree after legal-suffix/punctuation normalization.
    low_confidence = [
        direct_hint,
        raw_company,
        resolved_site_name,
        resolved_fallback,
        initial_site_name,
        initial_fallback,
    ]
    grouped: dict[str, list[str]] = {}
    for value in low_confidence:
        clean = _clean_company_label(value)
        key = _company_compare_key(clean)
        if key:
            grouped.setdefault(key, []).append(clean)
    matches = [values for values in grouped.values() if len(values) >= 2]
    if matches:
        return matches[0][0], "corroborated_page_metadata"

    return "Company", "unverified"


def _clean_job_title(value: str | None) -> str:
    label = _collapse_label(value)
    if not label:
        return ""
    low = label.lower()
    if low in _GENERIC_JOB_TITLES:
        return ""
    if re.fullmatch(r"(?i)(?:jobs?|careers?|recruitment)(?:\s+at\s+.+)?", label):
        return ""
    return label[:180]


def _heading_job_title(page: str) -> str:
    role_hint = re.compile(
        r"(?i)\b(data|analytics|engineer|engineering|developer|architect|scientist|platform|etl|database|software)\b"
    )
    for match in re.finditer(r"(?is)<h[12][^>]*>(.*?)</h[12]>", page or ""):
        candidate = _clean_job_title(_clean_html(match.group(1)))
        if candidate and role_hint.search(candidate):
            return candidate
    return ""


def _ats_company_hint(provider: str | None, identifier: str | None, url: str) -> str:
    if provider in {"workday", "greenhouse", "lever", "ashby", "smartrecruiters", "icims", "jobvite"}:
        label = _slug_label(identifier)
        if _clean_company_label(label):
            return _clean_company_label(label)
    host = (urlsplit(url or "").hostname or "").lower()
    if host and not any(vendor in host for vendor in _ATS_VENDOR_NAMES) and not any(
        host == agg or host.endswith("." + agg) for agg in _AGGREGATOR_HOSTS
    ):
        parts = [
            p for p in host.split(".")
            if p not in {"www", "jobs", "job", "careers", "career", "apply", "recruiting", "recruitment"}
        ]
        if parts:
            return _clean_company_label(_slug_label(parts[0]))
    return ""


def _ats_display(provider: str | None, identifier: str | None) -> tuple[str, str]:
    label = _PROVIDER_LABELS.get(provider or "", (provider or "Direct employer page").replace("_", " ").title())
    tenant = _slug_label(identifier)
    if tenant and tenant.lower() in _ATS_VENDOR_NAMES:
        tenant = ""
    return label, tenant


def _is_processing(row: dict) -> bool:
    return row.get("status") in _PROCESSING_STATUSES and row.get("application_status") != "SUBMITTED_CONFIRMED"


class LinksInput(BaseModel):
    links: list[str] | str


class ManualEdit(BaseModel):
    url: str | None = None
    company: str | None = None
    title: str | None = None
    location: str | None = None
    employment_type: str | None = None
    description: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict:
    with _STATE_LOCK:
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("jobs"), dict):
                return data
        except Exception:
            pass
        return {"version": 1, "jobs": {}}


def _save_state(data: dict) -> None:
    with _STATE_LOCK:
        MANUAL_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, STATE_FILE)


def _normalize_url(value: str) -> str:
    raw = (value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Job URL must use http:// or https://")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Local/private job URLs are not allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast):
        raise ValueError("Local/private job URLs are not allowed")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid job URL") from exc
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc += f":{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def _split_links(value: list[str] | str) -> list[str]:
    items = value if isinstance(value, list) else re.split(r"[\s]+", value or "")
    out, seen = [], set()
    for item in items:
        if not str(item).strip():
            continue
        url = _normalize_url(str(item))
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _key_for_url(url: str) -> str:
    digest = hashlib.sha256(_normalize_url(url).encode()).hexdigest()[:20]
    return f"manual:{digest}"


def _safe_key(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", key)


def _meta(page: str, name: str) -> str:
    q = re.escape(name)
    patterns = (
        rf'''(?is)<meta[^>]+(?:name|property)=["']{q}["'][^>]+content=["']([^"']+)["']''',
        rf'''(?is)<meta[^>]+content=["']([^"']+)["'][^>]+(?:name|property)=["']{q}["']''',
    )
    for pattern in patterns:
        m = re.search(pattern, page or "")
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def _page_title(page: str) -> str:
    value = _meta(page, "og:title") or _meta(page, "twitter:title")
    if value:
        return value
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", page or "")
    return _clean_html(m.group(1)) if m else ""


def _jsonld_metadata(page: str) -> dict:
    nodes = _jsonld_jobpostings(page)
    if not nodes:
        return {}
    node = max(nodes, key=lambda n: len(str(n.get("description") or "")))
    org = node.get("hiringOrganization")
    company = org.get("name") if isinstance(org, dict) else ""
    identifier = node.get("identifier")
    if isinstance(identifier, dict):
        identifier = identifier.get("value") or identifier.get("name")
    locations = []
    locs = node.get("jobLocation")
    locs = locs if isinstance(locs, list) else [locs] if isinstance(locs, dict) else []
    if str(node.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        locations.append("Remote")
    for loc in locs:
        address = loc.get("address") if isinstance(loc, dict) else None
        if not isinstance(address, dict):
            continue
        text = ", ".join(
            str(address.get(k)).strip()
            for k in ("addressLocality", "addressRegion", "addressCountry")
            if address.get(k)
        )
        if text and text not in locations:
            locations.append(text)
    return {
        "title": str(node.get("title") or node.get("name") or "").strip(),
        "company": str(company or "").strip(),
        "description": _clean_html(str(node.get("description") or "")),
        "location": " / ".join(locations),
        "employment_type": node.get("employmentType"),
        "posted_at": node.get("datePosted"),
        "requisition_id": str(identifier or "").strip() or None,
        "jsonld_url": str(node.get("url") or "").strip() or None,
    }


def _fallback_title_company(page: str) -> tuple[str, str]:
    text = _page_title(page)
    bits = [x.strip() for x in re.split(r"\s+[|–—-]\s+", text) if x.strip()]
    if not bits:
        return "", ""
    title = _clean_job_title(bits[0])
    company = next(
        (clean for value in reversed(bits[1:]) if (clean := _clean_company_label(value))),
        "",
    )
    # Aggregators often use titles such as "Data Engineer at Acme - Adzuna".
    if not company:
        match = re.search(r"(?i)\b(?:at|with)\s+(.+?)(?=\s+[|–—-]\s+|$)", text)
        if match:
            company = _clean_company_label(match.group(1))
            if company and title:
                title = re.sub(r"(?i)\s+\b(?:at|with)\s+.+$", "", title).strip()
    return (title or bits[0][:180]), company


def fetch_manual_job(url: str) -> dict:
    """Resolve exactly the supplied link into clean employer metadata and the best public JD."""
    submitted = _normalize_url(url)
    try:
        page = _fetch_public_page(submitted) or ""
    except Exception:
        page = ""

    initial_meta = _jsonld_metadata(page) if page else {}
    title_fallback, company_fallback = _fallback_title_company(page) if page else ("", "")
    description = (
        initial_meta.get("description")
        or (_best_resolved_description(page, "manual_link") if page else "")
        or ""
    )
    raw = {
        "external_id": _key_for_url(submitted),
        "source": "manual_link",
        "company_key": initial_meta.get("company") or (_meta(page, "og:site_name") if page else "") or company_fallback or "Unknown company",
        "company": initial_meta.get("company") or (_meta(page, "og:site_name") if page else "") or company_fallback or "Unknown company",
        "title": initial_meta.get("title") or _heading_job_title(page) or title_fallback or "Job from supplied link",
        "description": description,
        "location": initial_meta.get("location") or "",
        "employment_type": initial_meta.get("employment_type"),
        "posted_at": initial_meta.get("posted_at"),
        "requisition_id": initial_meta.get("requisition_id"),
        "url": submitted,
        "original_url": initial_meta.get("jsonld_url") or submitted,
        "submitted_url": submitted,
        "manual_link": True,
        "manual_filters_bypassed": True,
        "application_route": "MANUAL_LINK",
    }

    # This is resolution, not discovery: follow only the supplied job and the
    # employer/ATS destination it exposes, then ask the production JD finalizer
    # for the strongest public description for that same job.
    try:
        resolved = resolve_original_ats(raw)
        if isinstance(resolved, dict):
            raw = resolved
        resolved = resolve_full_jd(raw)
        if isinstance(resolved, dict):
            raw = resolved
    except Exception:
        pass

    effective = raw.get("original_url") or raw.get("url") or submitted
    provider, identifier = detect_ats(effective)
    provider = provider or raw.get("ats_provider")
    identifier = identifier or raw.get("ats_identifier")

    # Re-read the final employer/ATS detail page when resolution changed the URL.
    # Structured JobPosting data there is more reliable than portal titles such
    # as "Job Details", "Dayforce Jobs", or "Global Career Site".
    resolved_page = page
    if effective and effective != submitted:
        try:
            resolved_page = _fetch_public_page(effective) or page
        except Exception:
            resolved_page = page
    resolved_meta = _jsonld_metadata(resolved_page) if resolved_page else {}
    resolved_title_fallback, resolved_company_fallback = (
        _fallback_title_company(resolved_page) if resolved_page else ("", "")
    )

    company, company_source = _verified_company(
        resolved_meta=resolved_meta,
        initial_meta=initial_meta,
        provider=provider,
        identifier=identifier,
        effective_url=effective,
        submitted_url=submitted,
        raw_company=raw.get("company_key") or raw.get("company"),
        resolved_site_name=_meta(resolved_page, "og:site_name") if resolved_page else "",
        resolved_fallback=resolved_company_fallback,
        initial_site_name=_meta(page, "og:site_name") if page else "",
        initial_fallback=company_fallback,
    )

    title_candidates = [
        resolved_meta.get("title"),
        initial_meta.get("title"),
        raw.get("title"),
        _heading_job_title(resolved_page),
        resolved_title_fallback,
        _heading_job_title(page),
        title_fallback,
    ]
    title = next((clean for value in title_candidates if (clean := _clean_job_title(value))), "")
    if not title:
        title = "Job opening"

    descriptions = [
        str(raw.get("description") or "").strip(),
        str(resolved_meta.get("description") or "").strip(),
        str(initial_meta.get("description") or "").strip(),
        str(description or "").strip(),
    ]
    best_description = max(descriptions, key=len, default="")
    ats_label, ats_tenant = _ats_display(provider, identifier)

    raw["external_id"] = _key_for_url(submitted)
    raw["submitted_url"] = submitted
    raw["manual_link"] = True
    raw["manual_filters_bypassed"] = True
    raw["application_route"] = "MANUAL_LINK"
    raw["source"] = provider or raw.get("source") or "manual_link"
    raw["ats_provider"] = provider
    raw["ats_identifier"] = identifier
    raw["ats_label"] = ats_label
    raw["ats_tenant"] = ats_tenant
    raw["url"] = effective
    raw["original_url"] = effective
    raw["company_key"] = company
    raw["company"] = company
    raw["company_verified"] = company_source != "unverified"
    raw["company_source"] = company_source
    raw["title"] = title
    raw["description"] = best_description
    if resolved_meta.get("location"):
        raw["location"] = resolved_meta["location"]
    if resolved_meta.get("employment_type"):
        raw["employment_type"] = resolved_meta["employment_type"]
    if resolved_meta.get("requisition_id"):
        raw["requisition_id"] = resolved_meta["requisition_id"]

    complete = _looks_like_complete_jd(raw["description"], raw["source"])
    usable = complete or _looks_like_usable_jd(raw["description"], raw["source"])
    raw["description_complete"] = bool(complete)
    raw["description_usable"] = bool(usable)
    raw["tailoring_mode"] = "FULL_JD" if complete else "BASE_RESUME_CONSERVATIVE"
    raw["jd_fallback_reason"] = None if usable else (
        "No usable JD could be extracted from the supplied link or its resolved employer/ATS page; "
        "ignore this manual link and do not generate a resume."
    )
    return raw

def _bypass_eligibility() -> dict:
    item = {
        "eligible": True,
        "status": "BYPASSED_MANUAL_LINK",
        "reason": "Manual-link path intentionally bypasses discovery and eligibility filters.",
    }
    return {"eligible": True, "experience": dict(item), "sponsorship": dict(item), "manual_bypass": True}


def run_shared_resume_pipeline(raw: dict) -> dict:
    """Call the exact same batch_prepare.prepare used by production path 1."""
    key = raw["external_id"]
    attempt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe = _safe_key(key)
    work = WORK_DIR / safe / attempt
    report = work / "finalized.json"
    manifest = work / "manifest.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({
        "manual_path": True,
        "discovery_bypassed": True,
        "eligibility_filters_bypassed": True,
        "results": [{"action": "FINAL_JD_VERIFIED", "job": raw, "eligibility": _bypass_eligibility()}],
    }, indent=2), encoding="utf-8")
    old_draft, old_final = batch_prepare.DRAFT_RESUME_DIR, batch_prepare.FINAL_RESUME_DIR
    with _PREPARE_LOCK:
        try:
            batch_prepare.DRAFT_RESUME_DIR = str(work / "drafts")
            batch_prepare.FINAL_RESUME_DIR = str(ARTIFACT_DIR / safe / attempt)
            # Resume content selection, LLM prompting, retries, ATS audit, formatting,
            # and artifact validation are owned by the exact production path.
            rows = batch_prepare.prepare(str(report), str(manifest), external_id=key, limit=1)
        finally:
            batch_prepare.DRAFT_RESUME_DIR, batch_prepare.FINAL_RESUME_DIR = old_draft, old_final
    if not rows:
        raise RuntimeError("Shared resume pipeline returned no result.")
    return rows[0]


def _public(row: dict) -> dict:
    out = dict(row)
    out.pop("description", None)
    pdf = Path(str(row.get("pdf_path") or ""))
    out["resume_available"] = bool(row.get("pdf_path") and pdf.exists() and pdf.is_file())
    out["resume_url"] = f"/manual-resume/{row['key']}" if out["resume_available"] else None
    return out


def list_jobs() -> list[dict]:
    rows = [_public(x) for x in _load_state()["jobs"].values()]
    return sorted(rows, key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)


def add_links(value: list[str] | str) -> list[dict]:
    state = _load_state()
    out = []
    changed = False
    for url in _split_links(value):
        key = _key_for_url(url)
        if key in state["jobs"]:
            out.append(_public(state["jobs"][key]))
            continue
        now = _now()
        row = {
            "key": key, "external_id": key, "submitted_url": url, "url": url, "original_url": url,
            "company": "", "title": "", "location": "", "employment_type": None, "description": "",
            "source": "manual_link", "status": "PENDING", "application_status": "NOT_STARTED",
            "created_at": now, "updated_at": now, "error": None, "manual_filters_bypassed": True,
        }
        state["jobs"][key] = row
        out.append(_public(row))
        changed = True
    if changed:
        _save_state(state)
    return out


def _get(key: str) -> tuple[dict, dict]:
    state = _load_state()
    row = state["jobs"].get(key)
    if not row:
        raise HTTPException(404, "Manual job not found")
    return state, row


def process_job(key: str, force_refetch: bool = False) -> dict:
    state, row = _get(key)
    row["status"] = "FETCHING_JD" if force_refetch or not row.get("description_usable") else "GENERATING_RESUME"
    row["error"] = None
    row["updated_at"] = _now()
    state["jobs"][key] = row
    _save_state(state)
    try:
        if force_refetch or not row.get("description_usable") or not row.get("description"):
            raw = fetch_manual_job(row.get("submitted_url") or row.get("url"))
            if not force_refetch:
                for field in ("location", "employment_type"):
                    if row.get(field):
                        raw[field] = row[field]
        else:
            raw = {
                "external_id": key,
                "source": row.get("source") or "manual_link",
                "company_key": row.get("company") or "Unknown company",
                "company": row.get("company") or "Unknown company",
                "title": row.get("title") or "Job from supplied link",
                "description": row.get("description") or "",
                "location": row.get("location") or "",
                "employment_type": row.get("employment_type"),
                "url": row.get("url") or row.get("submitted_url"),
                "original_url": row.get("original_url") or row.get("url") or row.get("submitted_url"),
                "submitted_url": row.get("submitted_url"),
                "ats_provider": row.get("ats_provider"),
                "ats_identifier": row.get("ats_identifier"),
                "ats_label": row.get("ats_label"),
                "ats_tenant": row.get("ats_tenant"),
                "requisition_id": row.get("requisition_id"),
                "description_complete": bool(row.get("description_complete")),
                "description_usable": bool(row.get("description_usable")),
                "tailoring_mode": row.get("tailoring_mode") or "BASE_RESUME_CONSERVATIVE",
                "manual_link": True,
                "manual_filters_bypassed": True,
                "application_route": "MANUAL_LINK",
            }
        if not raw.get("description_usable") or not str(raw.get("description") or "").strip():
            row.update({
                "status": "IGNORED_NO_JD",
                "next_action": "IGNORED_NO_JD",
                "description": "",
                "description_usable": False,
                "description_complete": False,
                "source": raw.get("source") or row.get("source") or "manual_link",
                "url": raw.get("url") or row.get("url"),
                "original_url": raw.get("original_url") or row.get("original_url"),
                "ats_provider": raw.get("ats_provider"),
                "ats_identifier": raw.get("ats_identifier"),
                "ats_label": raw.get("ats_label") or _ats_display(raw.get("ats_provider"), raw.get("ats_identifier"))[0],
                "ats_tenant": raw.get("ats_tenant") or _ats_display(raw.get("ats_provider"), raw.get("ats_identifier"))[1],
                "error": None,
                "updated_at": _now(),
            })
            state = _load_state()
            if key in state["jobs"]:
                state["jobs"][key] = row
                _save_state(state)
            print(f"MANUAL IGNORE NO JD | {row.get('submitted_url') or row.get('url')}", flush=True)
            return _public(row)

        # A usable manual JD always enters the shared LLM tailoring path. This
        # flag only controls master-vs-tailored selection; prompts, retries, ATS
        # audit, formatting, and artifact validation remain the production code.
        raw["force_jd_tailoring"] = True

        clean_company = _clean_company_label(raw.get("company_key") or raw.get("company")) or "Company"
        clean_title = _clean_job_title(raw.get("title")) or "Job opening"
        raw["company_key"] = clean_company
        raw["company"] = clean_company
        raw["title"] = clean_title
        row.update({
            "company": clean_company,
            "title": clean_title,
            "location": raw.get("location") or "",
            "employment_type": raw.get("employment_type"),
            "description": raw.get("description") or "",
            "source": raw.get("source") or "manual_link",
            "url": raw.get("url") or row.get("url"),
            "original_url": raw.get("original_url") or row.get("original_url"),
            "ats_provider": raw.get("ats_provider"),
            "ats_identifier": raw.get("ats_identifier"),
            "ats_label": raw.get("ats_label") or _ats_display(raw.get("ats_provider"), raw.get("ats_identifier"))[0],
            "ats_tenant": raw.get("ats_tenant") or _ats_display(raw.get("ats_provider"), raw.get("ats_identifier"))[1],
            "requisition_id": raw.get("requisition_id"),
            "company_verified": bool(raw.get("company_verified")),
            "company_source": raw.get("company_source") or "unverified",
            "description_complete": bool(raw.get("description_complete")),
            "description_usable": bool(raw.get("description_usable")),
            "tailoring_mode": raw.get("tailoring_mode"),
            "status": "GENERATING_RESUME",
            "updated_at": _now(),
        })
        state = _load_state()
        state["jobs"][key] = row
        _save_state(state)
        result = run_shared_resume_pipeline(raw)
        row.update({
            "status": result.get("next_action") or "HOLD_RESUME_ERROR",
            "next_action": result.get("next_action"),
            "resume_path": result.get("resume_path"),
            "pdf_path": result.get("pdf_path"),
            "resume_tailoring_policy": result.get("resume_tailoring_policy"),
            "ats_audit": result.get("ats_audit"),
            "artifact_validation": result.get("artifact_validation"),
            "error": None if result.get("next_action") == "READY_TO_APPLY" else (result.get("ats_audit") or {}).get("error"),
            "updated_at": _now(),
        })
    except Exception as exc:
        row["status"] = "JD_FETCH_FAILED" if not row.get("description_usable") else "HOLD_RESUME_ERROR"
        row["error"] = str(exc)
        row["updated_at"] = _now()
    state = _load_state()
    if key in state["jobs"]:
        prior = state["jobs"][key]
        if prior.get("application_status") == "SUBMITTED_CONFIRMED":
            row["application_status"] = "SUBMITTED_CONFIRMED"
            row["submitted_at"] = prior.get("submitted_at")
        state["jobs"][key] = row
        _save_state(state)
    return _public(row)


def process_jobs(keys: list[str]) -> None:
    """Process one manual batch sequentially, with a volume-backed lock across deploy overlap."""
    with _BATCH_LOCK:
        lock_handle = None
        try:
            if fcntl is not None:
                MANUAL_DIR.mkdir(parents=True, exist_ok=True)
                lock_handle = (MANUAL_DIR / "batch.lock").open("a+", encoding="utf-8")
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            for key in keys:
                try:
                    _, row = _get(key)
                    if row.get("application_status") == "SUBMITTED_CONFIRMED" or row.get("status") == "READY_TO_APPLY":
                        continue
                    process_job(key)
                except Exception as exc:
                    print(f"MANUAL BACKGROUND ERROR {key}: {exc}", flush=True)
        finally:
            if lock_handle is not None:
                try:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                finally:
                    lock_handle.close()


def _company_is_aggregator(value: str | None) -> bool:
    low = _collapse_label(value).lower()
    return bool(low) and (
        low in _AGGREGATOR_NAMES
        or any(low == name or low.startswith(name + " ") for name in _AGGREGATOR_NAMES)
    )


def _recover_interrupted_jobs() -> list[str]:
    """Resume a manual batch after deploy/restart and retry the known stale-count failure."""
    state = _load_state()
    keys: list[str] = []
    changed = False
    for key, row in state["jobs"].items():
        if row.get("application_status") == "SUBMITTED_CONFIRMED":
            continue
        status = row.get("status")
        structural_retry = (
            status == "HOLD_RESUME_ERROR"
            and "must contain exactly" in str(row.get("error") or "").lower()
        )
        audit = row.get("ats_audit") or {}
        audit_structure_retry = (
            status == "HOLD_ATS_REVIEW"
            and (
                "structure" in (audit.get("blocking_quality_gates") or [])
                or (audit.get("quality_gates") or {}).get("structure") is False
            )
        )
        bad_ready_company = status == "READY_TO_APPLY" and _company_is_aggregator(row.get("company"))
        if bad_ready_company:
            row.update({
                "company": "",
                "description": "",
                "description_usable": False,
                "description_complete": False,
                "status": "PENDING",
                "next_action": None,
                "resume_path": None,
                "pdf_path": None,
                "error": None,
                "updated_at": _now(),
            })
            changed = True
        if status in _PROCESSING_STATUSES or structural_retry or audit_structure_retry or bad_ready_company:
            keys.append(key)
    if changed:
        _save_state(state)
    if keys:
        print(f"MANUAL STARTUP RECOVERY | jobs={len(keys)}", flush=True)
        threading.Thread(
            target=process_jobs,
            args=(keys,),
            daemon=True,
            name="manual-job-recovery",
        ).start()
    return keys


def reset_manual_state() -> int:
    """Delete only manual-link state/work/resumes and recreate an empty manual queue."""
    previous = len(_load_state().get("jobs") or {})
    shutil.rmtree(MANUAL_DIR, ignore_errors=True)
    _save_state({"version": 1, "jobs": {}})
    return previous


def _pause_active_manual_jobs() -> int:
    state = _load_state()
    paused = 0
    for row in state["jobs"].values():
        if row.get("status") in _PROCESSING_STATUSES:
            row["status"] = "PAUSED"
            row["error"] = None
            row["updated_at"] = _now()
            paused += 1
    if paused:
        _save_state(state)
    return paused


@router.on_event("startup")
def _startup_recover_manual_jobs() -> None:
    if os.getenv("MANUAL_RESET_ON_START", "").strip().lower() in {"1", "true", "yes", "on"}:
        deleted = reset_manual_state()
        print(f"MANUAL RESET COMPLETE | deleted={deleted}", flush=True)
        return
    if os.getenv("MANUAL_RECOVERY_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
        paused = _pause_active_manual_jobs()
        print(f"MANUAL STARTUP RECOVERY DISABLED | paused={paused}", flush=True)
        return
    _recover_interrupted_jobs()



def edit_job(key: str, body: ManualEdit) -> dict:
    state, row = _get(key)
    data = body.model_dump(exclude_unset=True)
    description_supplied = "description" in data
    if data.get("url"):
        normalized = _normalize_url(data["url"])
        data.update({
            "url": normalized, "submitted_url": normalized, "original_url": normalized,
            "description": "", "description_usable": False, "description_complete": False, "status": "PENDING",
        })
    if description_supplied:
        desc = (data.get("description") or "").strip()
        complete = _looks_like_complete_jd(desc, row.get("source") or "manual_link")
        usable = complete or _looks_like_usable_jd(desc, row.get("source") or "manual_link")
        data.update({
            "description": desc, "description_complete": bool(complete), "description_usable": bool(usable),
            "tailoring_mode": "FULL_JD" if complete else "BASE_RESUME_CONSERVATIVE",
            "status": "JD_READY" if usable else "JD_FETCH_FAILED",
        })
    for field in ("company", "title", "location", "employment_type"):
        if field in data and data[field] is not None:
            data[field] = str(data[field]).strip()
    for field in ("resume_path", "pdf_path", "ats_audit", "artifact_validation", "resume_tailoring_policy", "next_action"):
        row.pop(field, None)
    row.update(data)
    row["error"] = None
    row["updated_at"] = _now()
    state["jobs"][key] = row
    _save_state(state)
    return _public(row)


def delete_job(key: str) -> dict:
    state, row = _get(key)
    state["jobs"].pop(key, None)
    _save_state(state)
    shutil.rmtree(WORK_DIR / _safe_key(key), ignore_errors=True)
    shutil.rmtree(ARTIFACT_DIR / _safe_key(key), ignore_errors=True)
    return {"ok": True, "deleted": True, "key": key, "company": row.get("company"), "title": row.get("title")}


def confirm_submitted(key: str) -> dict:
    state, row = _get(key)
    row["application_status"] = "SUBMITTED_CONFIRMED"
    row["submitted_at"] = _now()
    row["updated_at"] = row["submitted_at"]
    state["jobs"][key] = row
    _save_state(state)
    return _public(row)


@router.get("/api/manual-links")
def api_list():
    all_rows = list_jobs()
    visible = [
        x for x in all_rows
        if x.get("status") == "READY_TO_APPLY"
        or x.get("application_status") == "SUBMITTED_CONFIRMED"
    ]
    processing_rows = [x for x in all_rows if _is_processing(x)]
    current = processing_rows[-1] if processing_rows else None
    terminal_hidden = [
        x for x in all_rows
        if x not in visible and not _is_processing(x)
    ]
    return {
        "jobs": visible,
        "current": current,
        "counts": {
            "total": len(all_rows),
            "ready": sum(
                x.get("status") == "READY_TO_APPLY"
                and x.get("application_status") != "SUBMITTED_CONFIRMED"
                for x in visible
            ),
            "applied": sum(x.get("application_status") == "SUBMITTED_CONFIRMED" for x in visible),
            "processing": len(processing_rows),
            "completed": len(visible),
            "hidden_terminal": len(terminal_hidden),
        },
    }


@router.post("/api/manual-links")
def api_add(body: LinksInput, background_tasks: BackgroundTasks):
    try:
        jobs = add_links(body.links)
        keys = [
            x["key"] for x in jobs
            if x.get("application_status") != "SUBMITTED_CONFIRMED"
            and x.get("status") != "READY_TO_APPLY"
        ]
        if keys:
            background_tasks.add_task(process_jobs, keys)
        return {"ok": True, "jobs": jobs, "queued": len(keys)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/api/manual-links/{key:path}/process")
def api_process(key: str, force_refetch: bool = False):
    return {"ok": True, "job": process_job(key, force_refetch)}


@router.patch("/api/manual-links/{key:path}")
def api_edit(key: str, body: ManualEdit):
    try:
        return {"ok": True, "job": edit_job(key, body)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/api/manual-links/{key:path}")
def api_delete(key: str):
    return delete_job(key)


@router.post("/api/manual-links/{key:path}/confirm-submitted")
def api_confirm(key: str):
    return {"ok": True, "job": confirm_submitted(key)}


@router.get("/manual-resume/{key:path}")
def manual_resume(key: str):
    _, row = _get(key)
    path = Path(str(row.get("pdf_path") or ""))
    if not row.get("pdf_path") or not path.exists() or not path.is_file() or path.suffix.lower() != ".pdf":
        raise HTTPException(404, "Resume not available")
    allowed, resolved = ARTIFACT_DIR.resolve(), path.resolve()
    if allowed != resolved and allowed not in resolved.parents:
        raise HTTPException(403, "Invalid manual resume path")
    return FileResponse(resolved, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{resolved.name}"'})


MANUAL_PAGE = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Manual Job Links</title><style>
:root{--bg:#07111f;--panel:#0c1828;--line:#21344a;--text:#edf3fb;--muted:#91a4bc}*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text);font-size:14px}.app{display:grid;grid-template-columns:210px minmax(0,1fr);min-height:100vh}.side{background:#0a1625;border-right:1px solid #1a2a3d;padding:22px 14px}.brand{font-size:20px;font-weight:850;padding:0 8px 24px}.brand small{display:block;color:var(--muted);font-size:11px;margin-top:4px}.nav{display:grid;gap:6px}.nav a{display:block;padding:11px 12px;border-radius:8px;color:#c7d2e2;text-decoration:none;font-size:13px}.nav .active,.nav a:hover{background:#173967;color:#fff}.main{padding:22px clamp(16px,2vw,30px) 36px;min-width:0}.top h1{font-size:23px;margin:0 0 5px}.muted{color:var(--muted);font-size:12px}.entry,.section{background:#0b1726;border:1px solid var(--line);border-radius:11px;margin:18px 0;overflow:hidden}.entry{padding:16px}.entry textarea{width:100%;min-height:112px;background:#0d1a2b;border:1px solid #263950;color:#eef4fc;border-radius:8px;padding:12px;resize:vertical}.toolbar{display:flex;gap:9px;align-items:center;margin-top:10px;flex-wrap:wrap}.btn{border:1px solid #30465f;background:#13253a;color:#dce7f5;padding:8px 10px;border-radius:7px;font-size:11px;font-weight:700;cursor:pointer;text-decoration:none}.btn.primary{background:#2f73df;border-color:#4388f4;color:#fff}.btn.danger{color:#ff8f91}.btn:disabled{opacity:.7;cursor:default}.processingPill{display:none;align-items:center;gap:7px;padding:7px 10px;border-radius:999px;background:#392d61;color:#d4c2ff;font-size:11px;font-weight:800}.processingPill.on{display:inline-flex}.dot{width:7px;height:7px;border-radius:50%;background:#c6a8ff;animation:pulse 1.1s infinite}@keyframes pulse{50%{opacity:.35}}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.stat{background:#0d1a2b;border:1px solid #263950;border-radius:10px;padding:15px}.stat span{color:#a9b8ca;font-size:11px}.stat b{display:block;font-size:24px;margin-top:5px}.sectionHead{padding:14px 16px;border-bottom:1px solid #1d3044;font-weight:800}.row{display:grid;grid-template-columns:minmax(300px,1.4fr) 150px 150px minmax(330px,.9fr);gap:14px;align-items:center;padding:14px 16px;border-bottom:1px solid #17283a;font-size:12px}.head{background:#101f31;color:#9fb0c7;font-size:10px;text-transform:uppercase}.title{font-weight:800;font-size:13px;margin-bottom:5px}.company{color:#d8e4f3;font-weight:700;font-size:12px;margin-bottom:4px}.meta{color:#8fa0b8;font-size:11px;overflow-wrap:anywhere}.badge{display:inline-flex;padding:5px 9px;border-radius:999px;font-size:10px;font-weight:800;background:#17304d}.ready{background:#0d4637;color:#62e5b0}.applied{background:#173b69;color:#74b4ff}.actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.empty{padding:30px;text-align:center;color:#8192a8}.note{margin-top:9px;color:#91a4bc;font-size:11px}.current{display:none;margin-top:10px;padding:9px 11px;border:1px solid #342c59;border-radius:8px;background:#17152a;color:#bba9de;font-size:11px}.current.on{display:block}@media(max-width:1050px){.app{grid-template-columns:1fr}.side{border-right:0;border-bottom:1px solid #1a2a3d}.nav{display:flex}.row{grid-template-columns:1fr 120px}.row>div:last-child{grid-column:1/-1}.actions{justify-content:flex-start}}@media(max-width:650px){.main{padding:12px}.stats{grid-template-columns:repeat(2,1fr)}.row{display:block}.head{display:none}.row>div{margin-bottom:8px}}
</style></head><body><div class="app"><aside class="side"><div class="brand">💼 Auto Apply<small>Job Application Manager</small></div><div class="nav"><a href="/">⌂ &nbsp; Job Discovery</a><a class="active" href="/manual-links">🔗 &nbsp; Manual Job Links</a></div></aside><main class="main"><div class="top"><h1>Manual Job Links</h1><div class="muted">Paste direct job links. Each link is resolved to its employer/ATS page. Links without a usable JD are ignored; accepted JDs enter the exact same production resume pipeline as Job Discovery.</div></div><section class="entry"><textarea id="links" placeholder="Paste one or many job links — one per line"></textarea><div class="toolbar"><button class="btn primary" id="addBtn">Add & Process</button><button class="btn" id="refreshBtn">Refresh</button><span class="processingPill" id="processingPill"><span class="dot"></span><span id="processingText">Still processing…</span></span></div><div class="current" id="currentJob"></div><div class="note">Jobs run sequentially in the order submitted. Only completed Ready to Apply resumes appear below. The first generated resume goes through the shared LLM/audit/retry pipeline and is shown when complete.</div></section><div class="stats"><div class="stat"><span>Submitted Links</span><b id="total">0</b></div><div class="stat"><span>Ready to Apply</span><b id="ready">0</b></div><div class="stat"><span>Applied</span><b id="applied">0</b></div><div class="stat"><span>Processing</span><b id="processing">0</b></div></div><section class="section"><div class="sectionHead">Ready to Apply</div><div class="row head"><div>Job</div><div>Status</div><div>Updated</div><div>Actions</div></div><div id="jobs"></div></section></main></div><script>
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let rows=[];
function nice(v){let d=new Date(v);return!v||isNaN(d)?"—":d.toLocaleString([],{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"})}
function ats(r){let label=r.ats_label||((r.ats_provider||"Direct employer page").replaceAll("_"," "));return r.ats_tenant?label+" · "+r.ats_tenant:label}
function syncBatch(d){let n=Number(d.counts?.processing||0),active=n>0;processing.textContent=n;addBtn.disabled=active;addBtn.textContent=active?"Processing…":"Add & Process";processingPill.classList.toggle("on",active);processingText.textContent=active?"Still processing · "+n+" remaining":"Still processing…";let cur=d.current;if(active&&cur){let stage=(cur.status||"PROCESSING").replaceAll("_"," ").toLowerCase();let who=cur.company||cur.title||"next submitted link";currentJob.textContent="Currently "+stage+": "+who;currentJob.classList.add("on")}else{currentJob.classList.remove("on");currentJob.textContent=""}}
async function load(){try{let d=await fetch("/api/manual-links",{cache:"no-store"}).then(r=>r.json());rows=d.jobs||[];total.textContent=d.counts.total||0;ready.textContent=d.counts.ready||0;applied.textContent=d.counts.applied||0;syncBatch(d);render()}catch(e){}}
function render(){jobs.innerHTML=rows.map(r=>{let applied=r.application_status==="SUBMITTED_CONFIRMED";return '<div class="row"><div><div class="title">'+esc(r.title||"Job opening")+'</div><div class="company">'+esc(r.company||"Company")+'</div><div class="meta">'+esc(ats(r))+(r.requisition_id?' · Req '+esc(r.requisition_id):'')+'</div></div><div><span class="badge '+(applied?'applied':'ready')+'">'+(applied?'Applied':'Ready to apply')+'</span></div><div>'+nice(r.updated_at)+'</div><div class="actions">'+(r.url?'<a class="btn primary" href="'+esc(r.url)+'" target="_blank">Open Job</a>':'')+(r.resume_url?'<a class="btn" href="'+esc(r.resume_url)+'" target="_blank">View Resume</a>':'')+(!applied?'<button class="btn" data-applied="'+esc(r.key)+'">✓ Mark Applied</button>':'')+'<button class="btn danger" data-delete="'+esc(r.key)+'">Delete</button></div></div>'}).join("")||'<div class="empty">No completed resumes yet. When processing finishes for a job, it will appear here automatically.</div>'}
addBtn.onclick=async()=>{let text=links.value.trim();if(!text||addBtn.disabled)return;addBtn.disabled=true;addBtn.textContent="Processing…";processingPill.classList.add("on");processingText.textContent="Starting batch…";try{let r=await fetch("/api/manual-links",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({links:text})});let d=await r.json();if(!r.ok)throw new Error(d.detail||"Could not add links");links.value="";await load()}catch(e){alert(e.message);addBtn.disabled=false;addBtn.textContent="Add & Process";processingPill.classList.remove("on")}}
refreshBtn.onclick=load;
jobs.onclick=async e=>{let a=e.target.closest("[data-applied]");if(a){if(confirm("Mark this application as Applied?")){await fetch("/api/manual-links/"+encodeURIComponent(a.dataset.applied)+"/confirm-submitted",{method:"POST"});await load()}return}let d=e.target.closest("[data-delete]");if(d){if(confirm("Delete only this manual job and its resume?")){await fetch("/api/manual-links/"+encodeURIComponent(d.dataset.delete),{method:"DELETE"});await load()}}};
load();setInterval(load,3000);
</script></body></html>'''

@router.get("/manual-links", response_class=HTMLResponse)
def manual_page():
    return HTMLResponse(MANUAL_PAGE)
