from __future__ import annotations

import html
import json
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

UA={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/html,*/*"}

def _get(url: str, timeout: int=25) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _plain(value) -> str:
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",html.unescape(str(value or "")))).strip()

def _tenant(url: str) -> str:
    host=(urlparse(str(url or "")).hostname or "").lower()
    return host.split(".",1)[0] if host.endswith(".bamboohr.com") else ""

def _location(row: dict) -> str | None:
    for key in ("location","atsLocation"):
        value=row.get(key)
        if not isinstance(value,dict):
            continue
        parts=[value.get("city"),value.get("state") or value.get("province"),value.get("country")]
        text=", ".join(str(x).strip() for x in parts if x)
        if text:
            return text
    return "Remote" if str(row.get("locationType") or "")=="1" or row.get("isRemote") is True else None

def fetch_job(company: str, url: str, timeout: int=25) -> dict | None:
    """Resolve one exact BambooHR job through its zero-auth public detail endpoint."""
    tenant=_tenant(url)
    m=re.search(r"/careers/(\d+)",str(url or ""),re.I)
    if not tenant or not m:
        return None
    job_id=m.group(1)
    detail=f"https://{tenant}.bamboohr.com/careers/{job_id}/detail"
    try:
        payload=json.loads(_get(detail,timeout))
    except Exception:
        return None
    row=((payload.get("result") or {}).get("jobOpening") or {}) if isinstance(payload,dict) else {}
    if not isinstance(row,dict) or not row.get("jobOpeningName"):
        return None
    desc=_plain(row.get("description"))
    canonical=str(row.get("jobOpeningShareUrl") or f"https://{tenant}.bamboohr.com/careers/{job_id}")
    resolved_company=company or tenant
    return {
        "external_id":f"bamboohr:{tenant}:{job_id}",
        "source":"bamboohr",
        "company_key":resolved_company,
        "company":resolved_company,
        "title":str(row.get("jobOpeningName") or "").strip(),
        "location":_location(row),
        "employment_type":row.get("employmentStatusLabel") or row.get("employmentType"),
        "url":canonical,
        "original_url":canonical,
        "ats_provider":"bamboohr",
        "ats_identifier":tenant,
        "job_id":job_id,
        "requisition_id":job_id,
        "description":desc,
        "description_complete":bool(desc),
        "posted_at":row.get("datePosted"),
        "exact_job_metadata_source":"bamboohr_public_detail_api",
    }

def fetch_jobs(company: str, search_url: str, timeout: int=25) -> list[dict]:
    """Enumerate BambooHR public jobs and enrich matching data roles with exact details."""
    tenant=_tenant(search_url)
    if not tenant:
        return []
    try:
        payload=json.loads(_get(f"https://{tenant}.bamboohr.com/careers/list",timeout))
    except Exception:
        return []
    out=[]
    terms=("data engineer","data engineering","data platform engineer","data infrastructure engineer","etl engineer","analytics engineer","ml data engineer")
    for row in payload.get("result") or []:
        if not isinstance(row,dict):
            continue
        title=str(row.get("jobOpeningName") or "").strip()
        if not any(term in title.lower() for term in terms):
            continue
        job_id=str(row.get("id") or "").strip()
        if not job_id:
            continue
        exact=fetch_job(company or tenant,f"https://{tenant}.bamboohr.com/careers/{job_id}",timeout)
        if exact:
            out.append(exact)
        else:
            out.append({
                "external_id":f"bamboohr:{tenant}:{job_id}",
                "source":"bamboohr",
                "company_key":company or tenant,
                "title":title,
                "location":_location(row),
                "employment_type":row.get("employmentStatusLabel") or row.get("employmentType"),
                "url":f"https://{tenant}.bamboohr.com/careers/{job_id}",
                "original_url":f"https://{tenant}.bamboohr.com/careers/{job_id}",
                "ats_provider":"bamboohr",
                "ats_identifier":tenant,
                "job_id":job_id,
                "description":"",
                "description_complete":False,
            })
    return out
