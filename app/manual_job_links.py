from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import os
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException
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
    return bits[0][:180], (bits[-1][:180] if len(bits) > 1 else "")


def fetch_manual_job(url: str) -> dict:
    """Resolve only the supplied job link. No discovery run or eligibility filtering."""
    submitted = _normalize_url(url)
    page = _fetch_public_page(submitted)
    if not page:
        raise RuntimeError("Could not read the supplied job page. Edit the row, paste the JD, and retry.")
    meta = _jsonld_metadata(page)
    title_fallback, company_fallback = _fallback_title_company(page)
    description = meta.get("description") or _best_resolved_description(page, "manual_link")
    raw = {
        "external_id": _key_for_url(submitted),
        "source": "manual_link",
        "company_key": meta.get("company") or _meta(page, "og:site_name") or company_fallback or "Unknown company",
        "company": meta.get("company") or _meta(page, "og:site_name") or company_fallback or "Unknown company",
        "title": meta.get("title") or title_fallback or "Job from supplied link",
        "description": description,
        "location": meta.get("location") or "",
        "employment_type": meta.get("employment_type"),
        "posted_at": meta.get("posted_at"),
        "requisition_id": meta.get("requisition_id"),
        "url": submitted,
        "original_url": meta.get("jsonld_url") or submitted,
        "submitted_url": submitted,
        "manual_link": True,
        "manual_filters_bypassed": True,
        "application_route": "MANUAL_LINK",
    }
    # Reuse the existing exact-link/ATS JD resolver only. This does not execute
    # daily discovery, target-company filtering, sponsorship, experience, or freshness gates.
    try:
        raw = resolve_original_ats(raw)
        raw = resolve_full_jd(raw)
    except Exception:
        pass
    raw["external_id"] = _key_for_url(submitted)
    raw["submitted_url"] = submitted
    raw["manual_link"] = True
    raw["manual_filters_bypassed"] = True
    raw["application_route"] = "MANUAL_LINK"
    effective = raw.get("original_url") or raw.get("url") or submitted
    provider, identifier = detect_ats(effective)
    raw["source"] = provider or raw.get("source") or "manual_link"
    raw["ats_provider"] = provider or raw.get("ats_provider")
    raw["ats_identifier"] = identifier or raw.get("ats_identifier")
    raw["url"] = effective
    raw["original_url"] = effective
    raw["description"] = (raw.get("description") or description or "").strip()
    complete = _looks_like_complete_jd(raw["description"], raw["source"])
    usable = complete or _looks_like_usable_jd(raw["description"], raw["source"])
    raw["description_complete"] = bool(complete)
    raw["description_usable"] = bool(usable)
    raw["tailoring_mode"] = "FULL_JD" if complete else "BASE_RESUME_CONSERVATIVE"
    if not usable:
        raise RuntimeError("The supplied page did not expose a usable JD. Edit the row, paste the JD, and retry.")
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
                for field in ("company", "title", "location", "employment_type"):
                    if row.get(field):
                        raw[field] = row[field]
                        if field == "company":
                            raw["company_key"] = row[field]
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
                "requisition_id": row.get("requisition_id"),
                "description_complete": bool(row.get("description_complete")),
                "description_usable": bool(row.get("description_usable")),
                "tailoring_mode": row.get("tailoring_mode") or "BASE_RESUME_CONSERVATIVE",
                "manual_link": True,
                "manual_filters_bypassed": True,
                "application_route": "MANUAL_LINK",
            }
        row.update({
            "company": raw.get("company_key") or raw.get("company") or "Unknown company",
            "title": raw.get("title") or "Job from supplied link",
            "location": raw.get("location") or "",
            "employment_type": raw.get("employment_type"),
            "description": raw.get("description") or "",
            "source": raw.get("source") or "manual_link",
            "url": raw.get("url") or row.get("url"),
            "original_url": raw.get("original_url") or row.get("original_url"),
            "ats_provider": raw.get("ats_provider"),
            "ats_identifier": raw.get("ats_identifier"),
            "requisition_id": raw.get("requisition_id"),
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


def edit_job(key: str, body: ManualEdit) -> dict:
    state, row = _get(key)
    data = body.model_dump(exclude_unset=True)
    if data.get("url"):
        normalized = _normalize_url(data["url"])
        data.update({
            "url": normalized, "submitted_url": normalized, "original_url": normalized,
            "description": "", "description_usable": False, "description_complete": False, "status": "PENDING",
        })
    if "description" in data:
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
    rows = list_jobs()
    attention_states = {"JD_FETCH_FAILED", "HOLD_RESUME_ERROR", "HOLD_ATS_REVIEW", "HOLD_ARTIFACT_VALIDATION", "RETRY_RESUME_GENERATION"}
    return {"jobs": rows, "counts": {
        "total": len(rows),
        "ready": sum(x.get("status") == "READY_TO_APPLY" for x in rows),
        "applied": sum(x.get("application_status") == "SUBMITTED_CONFIRMED" for x in rows),
        "needs_attention": sum(x.get("status") in attention_states for x in rows),
    }}


@router.post("/api/manual-links")
def api_add(body: LinksInput):
    try:
        return {"ok": True, "jobs": add_links(body.links)}
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
:root{--bg:#07111f;--panel:#0c1828;--line:#21344a;--text:#edf3fb;--muted:#91a4bc}*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text);font-size:14px}.app{display:grid;grid-template-columns:210px minmax(0,1fr);min-height:100vh}.side{background:#0a1625;border-right:1px solid #1a2a3d;padding:22px 14px}.brand{font-size:20px;font-weight:850;padding:0 8px 24px}.brand small{display:block;color:var(--muted);font-size:11px;margin-top:4px}.nav{display:grid;gap:6px}.nav a{display:block;padding:11px 12px;border-radius:8px;color:#c7d2e2;text-decoration:none;font-size:13px}.nav .active,.nav a:hover{background:#173967;color:#fff}.main{padding:22px clamp(16px,2vw,30px) 36px;min-width:0}.top h1{font-size:23px;margin:0 0 5px}.muted{color:var(--muted);font-size:12px}.entry,.section{background:#0b1726;border:1px solid var(--line);border-radius:11px;margin:18px 0;overflow:hidden}.entry{padding:16px}.entry textarea{width:100%;min-height:112px;background:#0d1a2b;border:1px solid #263950;color:#eef4fc;border-radius:8px;padding:12px;resize:vertical}.toolbar{display:flex;gap:8px;align-items:center;margin-top:10px}.btn{border:1px solid #30465f;background:#13253a;color:#dce7f5;padding:8px 10px;border-radius:7px;font-size:11px;font-weight:700;cursor:pointer;text-decoration:none}.btn.primary{background:#2f73df;border-color:#4388f4;color:#fff}.btn.danger{color:#ff8f91}.btn:disabled{opacity:.55}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.stat{background:#0d1a2b;border:1px solid #263950;border-radius:10px;padding:15px}.stat span{color:#a9b8ca;font-size:11px}.stat b{display:block;font-size:24px;margin-top:5px}.sectionHead{padding:14px 16px;border-bottom:1px solid #1d3044;font-weight:800}.row{display:grid;grid-template-columns:minmax(260px,1.2fr) 145px 150px minmax(420px,1fr);gap:14px;align-items:center;padding:14px 16px;border-bottom:1px solid #17283a;font-size:12px}.head{background:#101f31;color:#9fb0c7;font-size:10px;text-transform:uppercase}.title{font-weight:800;font-size:13px;margin-bottom:5px}.meta{color:#8fa0b8;font-size:11px;overflow-wrap:anywhere}.error{color:#ff9fa1;font-size:11px;margin-top:5px}.badge{display:inline-flex;padding:5px 9px;border-radius:999px;font-size:10px;font-weight:800;background:#17304d}.ready{background:#0d4637;color:#62e5b0}.applied{background:#173b69;color:#74b4ff}.attention{background:#522d31;color:#ff9fa1}.working{background:#392d61;color:#c6a8ff}.actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.empty{padding:26px;text-align:center;color:#8192a8}.note{margin-top:8px;color:#91a4bc;font-size:11px}.progress{display:none;color:#a9b8ca}.progress.on{display:inline}@media(max-width:1050px){.app{grid-template-columns:1fr}.side{border-right:0;border-bottom:1px solid #1a2a3d}.nav{display:flex}.row{grid-template-columns:1fr 120px}.row>div:last-child{grid-column:1/-1}.actions{justify-content:flex-start}}@media(max-width:650px){.main{padding:12px}.stats{grid-template-columns:repeat(2,1fr)}.row{display:block}.head{display:none}.row>div{margin-bottom:8px}}
</style></head><body><div class="app"><aside class="side"><div class="brand">💼 Auto Apply<small>Job Application Manager</small></div><div class="nav"><a href="/">⌂ &nbsp; Job Discovery</a><a class="active" href="/manual-links">🔗 &nbsp; Manual Job Links</a></div></aside><main class="main"><div class="top"><h1>Manual Job Links</h1><div class="muted">Paste direct job links. This path skips discovery and eligibility filters and uses the same production resume-generation and validation rules.</div></div><section class="entry"><textarea id="links" placeholder="Paste one or many job links — one per line"></textarea><div class="toolbar"><button class="btn primary" id="addBtn">Add & Process</button><button class="btn" id="refreshBtn">Refresh</button><span class="progress" id="progress">Processing…</span></div><div class="note">If a site blocks JD extraction, Edit the row and paste the JD, then Process / Retry. The existing discovery path is untouched.</div></section><div class="stats"><div class="stat"><span>Total Links</span><b id="total">0</b></div><div class="stat"><span>Ready to Apply</span><b id="ready">0</b></div><div class="stat"><span>Applied</span><b id="applied">0</b></div><div class="stat"><span>Needs Attention</span><b id="attention">0</b></div></div><section class="section"><div class="sectionHead">Manual Resume Queue</div><div class="row head"><div>Job</div><div>Status</div><div>Updated</div><div>Actions</div></div><div id="jobs"></div></section></main></div><script>
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));let rows=[],busy=new Set();function st(r){if(r.application_status==="SUBMITTED_CONFIRMED")return["Applied","applied"];if(r.status==="READY_TO_APPLY")return["Ready to apply","ready"];if(["PENDING","JD_READY","FETCHING_JD","GENERATING_RESUME"].includes(r.status))return[(r.status||"").replaceAll("_"," "),"working"];return[(r.status||"Needs attention").replaceAll("_"," "),"attention"]}function nice(v){let d=new Date(v);return!v||isNaN(d)?"—":d.toLocaleString([],{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"})}async function load(){let d=await fetch("/api/manual-links",{cache:"no-store"}).then(r=>r.json());rows=d.jobs||[];total.textContent=d.counts.total;ready.textContent=d.counts.ready;applied.textContent=d.counts.applied;attention.textContent=d.counts.needs_attention;render()}function render(){jobs.innerHTML=rows.map(r=>{let s=st(r);return '<div class="row"><div><div class="title">'+esc(r.title||"Job link pending")+'</div><div class="meta">'+esc(r.company||"Company pending")+' · '+esc(r.source||"manual_link")+'</div><div class="meta">'+esc(r.submitted_url||r.url||"")+'</div>'+(r.error?'<div class="error">'+esc(r.error)+'</div>':'')+'</div><div><span class="badge '+s[1]+'">'+esc(s[0])+'</span></div><div>'+nice(r.updated_at)+'</div><div class="actions">'+(r.url?'<a class="btn primary" href="'+esc(r.url)+'" target="_blank">Open Job</a>':'')+(r.resume_url?'<a class="btn" href="'+esc(r.resume_url)+'" target="_blank">View Resume</a>':'')+(r.application_status!=="SUBMITTED_CONFIRMED"?'<button class="btn" data-process="'+esc(r.key)+'" '+(busy.has(r.key)?'disabled':'')+'>'+(r.status==="READY_TO_APPLY"?"Regenerate":"Process / Retry")+'</button>':'')+'<button class="btn" data-edit="'+esc(r.key)+'">Edit</button>'+(r.status==="READY_TO_APPLY"&&r.application_status!=="SUBMITTED_CONFIRMED"?'<button class="btn" data-applied="'+esc(r.key)+'">✓ Mark Applied</button>':'')+'<button class="btn danger" data-delete="'+esc(r.key)+'">Delete</button></div></div>'}).join("")||'<div class="empty">No manual job links yet.</div>'}async function processOne(key){busy.add(key);render();try{let r=await fetch("/api/manual-links/"+encodeURIComponent(key)+"/process",{method:"POST"});let d=await r.json();if(!r.ok)throw new Error(d.detail||"Processing failed")}catch(e){alert(e.message)}finally{busy.delete(key);await load()}}addBtn.onclick=async()=>{let text=links.value.trim();if(!text)return;addBtn.disabled=true;progress.classList.add("on");try{let r=await fetch("/api/manual-links",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({links:text})});let d=await r.json();if(!r.ok)throw new Error(d.detail||"Could not add links");links.value="";for(let j of d.jobs||[]){if(j.application_status!=="SUBMITTED_CONFIRMED")await processOne(j.key)}}catch(e){alert(e.message)}finally{addBtn.disabled=false;progress.classList.remove("on");await load()}};refreshBtn.onclick=load;jobs.onclick=async e=>{let p=e.target.closest("[data-process]");if(p){await processOne(p.dataset.process);return}let a=e.target.closest("[data-applied]");if(a){if(confirm("Mark this application as Applied?")){await fetch("/api/manual-links/"+encodeURIComponent(a.dataset.applied)+"/confirm-submitted",{method:"POST"});await load()}return}let d=e.target.closest("[data-delete]");if(d){if(confirm("Delete only this manual job and its resume?")){await fetch("/api/manual-links/"+encodeURIComponent(d.dataset.delete),{method:"DELETE"});await load()}return}let b=e.target.closest("[data-edit]");if(b){let r=rows.find(x=>x.key===b.dataset.edit);if(!r)return;let url=prompt("Job URL",r.submitted_url||r.url||"");if(url===null)return;let company=prompt("Company",r.company||"");if(company===null)return;let title=prompt("Job title",r.title||"");if(title===null)return;let location=prompt("Location",r.location||"");if(location===null)return;let jd=prompt("Paste a replacement JD to override the fetched JD. Leave blank to keep the current JD.","");let body={url,company,title,location};if(jd&&jd.trim())body.description=jd.trim();let x=await fetch("/api/manual-links/"+encodeURIComponent(r.key),{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});if(!x.ok){let y=await x.json();alert(y.detail||"Edit failed")}await load()}};load();setInterval(load,15000);
</script></body></html>'''


@router.get("/manual-links", response_class=HTMLResponse)
def manual_page():
    return HTMLResponse(MANUAL_PAGE)
