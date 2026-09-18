from __future__ import annotations
import hashlib, re
from urllib.parse import urlsplit, urlunsplit

LEGAL_SUFFIXES=re.compile(r"\b(incorporated|inc|corp|corporation|llc|ltd|limited|company|co)\b",re.I)

def _norm(value):
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",(value or "").lower())).strip()

def normalize_company(value):
    return re.sub(r"\s+"," ",LEGAL_SUFFIXES.sub(" ",_norm(value))).strip()

def normalize_title(value):
    text=re.sub(r"\([^)]*\)"," ",value or "")
    text=re.sub(r"\b(remote|hybrid|on[- ]?site|onsite)\b"," ",text,flags=re.I)
    return _norm(text)

def normalize_url(value):
    if not value:return ""
    try:
        p=urlsplit(value)
        return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip("/"),"", ""))
    except Exception:return value

def canonical_job_key(job):
    """Stable identity for cross-source/cross-hour dedup; prefer employer requisition IDs."""
    employer=normalize_company(job.get("company_key") or job.get("company"))
    req=str(job.get("requisition_id") or job.get("job_id") or job.get("ats_job_id") or "").strip().lower()
    if employer and req:return f"req:{employer}:{req}"
    title=normalize_title(job.get("title"))
    loc=_norm(job.get("location"))
    url=normalize_url(job.get("original_url") or job.get("url"))
    raw="|".join((employer,title,loc,url))
    return "job:"+hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
