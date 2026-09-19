from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import hashlib
from app.job_identity import canonical_job_key, identity_keys

DEFAULT_LEDGER=Path("generated/job_ledger.json")

def load_ledger(path=DEFAULT_LEDGER):
    p=Path(path)
    if not p.exists():return {"schema_version":2,"jobs":{},"aliases":{}}
    try:
        data=json.loads(p.read_text(encoding="utf-8"));data.setdefault("schema_version",2);data.setdefault("jobs",{});data.setdefault("aliases",{});return data
    except Exception:return {"schema_version":2,"jobs":{},"aliases":{}}

def save_ledger(ledger,path=DEFAULT_LEDGER):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(ledger,indent=2),encoding="utf-8")

def _lookup(job,ledger):
    jobs=ledger.get("jobs",{});aliases=ledger.get("aliases",{})
    for candidate in identity_keys(job):
        key=aliases.get(candidate,candidate);row=jobs.get(key)
        if row:return key,row
    return canonical_job_key(job),None

LIFECYCLE_STATUSES={
    "DISCOVERED","FILTERED_OUT","ELIGIBLE","JD_RESOLVED","FINAL_JD_VERIFIED",
    "RESUME_GENERATED","RESUME_VALIDATED","QUEUED","APPLICATION_STARTED",
    "SUBMITTED_CONFIRMED","SUBMISSION_UNCONFIRMED","BLOCKED","FAILED",
    # Backward-compatible statuses already emitted by the current pipeline.
    "READY_TO_APPLY","HOLD_ATS_REVIEW","HOLD_ARTIFACT_VALIDATION","HOLD_RESUME_ERROR",
    "SUBMITTED","MANUAL_ACTION_REQUIRED","IN_PROGRESS","PERMANENT_SKIP","PREPARED",
}

def _description_hash(job):
    description=(job.get("description") or "").strip()
    return hashlib.sha256(description.encode("utf-8")).hexdigest() if description else None

PROCESSED_STATUSES={
    # FINAL_JD_VERIFIED is intentionally NOT terminal: a free discovery/finalization
    # cycle must not prevent a later paid resume-generation cycle from processing it.
    "READY_TO_APPLY","HOLD_ATS_REVIEW","HOLD_RESUME_ERROR",
    "SUBMITTED","MANUAL_ACTION_REQUIRED","IN_PROGRESS","PERMANENT_SKIP",
}

def seen_or_submitted(job,ledger):
    key,row=_lookup(job,ledger)
    return bool(row and row.get("application_status") in PROCESSED_STATUSES),key,row

def record_seen(job,ledger,status="DISCOVERED",**extra):
    key,existing=_lookup(job,ledger);now=datetime.now(timezone.utc).isoformat()
    jobs=ledger.setdefault("jobs",{});row=existing or jobs.setdefault(key,{"first_seen":now,"first_seen_at":now})
    aliases=ledger.setdefault("aliases",{})
    for alias in identity_keys(job):aliases[alias]=key
    row.update({"last_seen":now,"last_seen_at":now,"company":job.get("company_key") or job.get("company"),"title":job.get("title"),
                "source":job.get("source"),"ats":job.get("ats_provider") or job.get("ats"),"external_job_id":job.get("external_id") or job.get("job_id"),
                "location":job.get("location"),"job_url":job.get("original_url") or job.get("url"),"apply_url":job.get("apply_url") or job.get("url"),
                "url":job.get("original_url") or job.get("url"),"posted_at":job.get("posted_at"),
                "description_hash":job.get("description_hash") or job.get("jd_hash") or _description_hash(job),
                "application_status":status})
    sources=set(row.get("sources") or []);sources.add(job.get("source") or "unknown");row["sources"]=sorted(sources)
    external_ids=set(row.get("external_ids") or []);external_ids.add(job.get("external_id") or "");row["external_ids"]=sorted(x for x in external_ids if x)
    row.update(extra);return key
