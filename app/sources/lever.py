from __future__ import annotations
import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode

BASE = "https://api.lever.co/v0/postings"

def fetch_jobs(site: str, timeout: int = 20) -> list[dict]:
    """Fetch public Lever postings for one company site."""
    url = f"{BASE}/{site}?{urlencode({'mode':'json','limit':100})}"
    req = Request(url, headers={"Accept":"application/json","User-Agent":"AI-Job-Search-Agent/0.2"})
    with urlopen(req, timeout=timeout) as resp:
        payload=json.loads(resp.read().decode("utf-8"))
    out=[]
    for j in payload:
        lists=j.get("lists") or []
        description=" ".join([j.get("descriptionPlain") or "", j.get("additionalPlain") or ""] + [x.get("content","") for x in lists])
        cats=j.get("categories") or {}
        out.append({
            "external_id": f"lever:{site}:{j.get('id')}",
            "source":"lever",
            "company_key":site,
            "title":j.get("text",""),
            "location":cats.get("location"),
            "url":j.get("hostedUrl") or j.get("applyUrl"),
            "description":description,
            "updated_at":None,
        })
    return out


def fetch_job(company: str, url: str, timeout: int = 20) -> dict | None:
    """Resolve one exact Lever posting through Lever's public postings API."""
    from urllib.parse import urlparse
    import re

    parsed=urlparse(str(url or ""))
    parts=[x for x in parsed.path.split("/") if x]
    if len(parts)<2:
        return None
    site=parts[0]
    posting_id=parts[1]
    if not re.fullmatch(r"[0-9a-fA-F-]{20,}", posting_id):
        return None
    api=f"{BASE}/{site}/{posting_id}?{urlencode({'mode':'json'})}"
    req=Request(api,headers={"Accept":"application/json","User-Agent":"AI-Job-Search-Agent/0.2"})
    try:
        with urlopen(req,timeout=timeout) as resp:
            j=json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(j,dict) or not j.get("text"):
        return None
    lists=j.get("lists") or []
    description=" ".join(
        [j.get("descriptionPlain") or "", j.get("additionalPlain") or ""]
        + [x.get("content","") for x in lists if isinstance(x,dict)]
    ).strip()
    cats=j.get("categories") or {}
    return {
        "external_id":f"lever:{site}:{j.get('id') or posting_id}",
        "source":"lever",
        "company_key":company or site,
        "company":company or site,
        "title":j.get("text",""),
        "location":cats.get("location"),
        "url":j.get("hostedUrl") or f"https://jobs.lever.co/{site}/{posting_id}",
        "original_url":j.get("hostedUrl") or f"https://jobs.lever.co/{site}/{posting_id}",
        "ats_provider":"lever",
        "ats_identifier":site,
        "job_id":j.get("id") or posting_id,
        "requisition_id":j.get("id") or posting_id,
        "description":description,
        "description_complete":bool(description),
        "exact_job_metadata_source":"lever_public_posting_api",
    }
