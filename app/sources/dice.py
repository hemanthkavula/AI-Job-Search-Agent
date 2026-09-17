from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from app.sources.mcp_jobs import call_tool, rows_from_payload

ENDPOINT = "https://mcp.dice.com/mcp"
SEARCH_TERMS = (
    "Data Engineer","Senior Data Engineer","Lead Data Engineer","Staff Data Engineer","Principal Data Engineer",
    "AWS Data Engineer","Azure Data Engineer","Cloud Data Engineer","Big Data Engineer","Data Platform Engineer",
    "Data Infrastructure Engineer","Data Pipeline Engineer","ETL Data Engineer","Analytics Data Engineer",
)

def _iso(value):
    if not value:return None
    text=str(value).strip()
    try:return datetime.fromisoformat(text.replace("Z","+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:return text

def _stringify_location(value):
    if isinstance(value,dict):
        return ", ".join(str(value.get(k)) for k in ("city","state","country") if value.get(k))
    return value

def _normalize(row: dict) -> dict:
    url=row.get("detailsPageUrl") or row.get("url") or row.get("jobUrl") or ""
    raw_id=row.get("id") or row.get("jobId") or url or f"{row.get('companyName')}:{row.get('title')}:{row.get('postedDate')}"
    stable=hashlib.sha1(str(raw_id).encode("utf-8")).hexdigest()[:20]
    location=_stringify_location(row.get("jobLocation") or row.get("location"))
    description=row.get("description") or row.get("jobDescription") or row.get("summary") or ""
    workplace=row.get("workplaceTypes") or row.get("workplaceType") or row.get("workplace_types")
    return {
        "external_id":f"dice:{stable}","source":"dice","company_key":row.get("companyName") or row.get("company") or "Unknown",
        "title":row.get("title") or row.get("jobTitle") or "","location":location,
        "employment_type":row.get("employmentType") or row.get("employment_type") or "FULLTIME","workplace_type":workplace,
        "url":url,"company_url":row.get("companyPageUrl") or "","description":description,
        "description_complete":bool(description and len(description.strip()) >= 500),
        "updated_at":_iso(row.get("postedDate") or row.get("posted_at") or row.get("datePosted")),
        "posted_on":row.get("postedDate") or row.get("datePosted"),
        "sponsorship_signal":row.get("willingToSponsor") if "willingToSponsor" in row else row.get("willing_to_sponsor"),
        "provider_us_scoped":True,"provider_fulltime_scoped":True,
    }

def fetch_jobs(jobs_per_page: int = 100) -> list[dict]:
    """Search Dice's official MCP for US full-time DE-family jobs posted in one day.

    Dice documents search_jobs as returning detailed descriptions, locations, employment
    types, skills and direct application links, so retain those fields for the final
    local eligibility pass rather than making an unsupported second MCP call.
    """
    dedup={}
    for keyword in SEARCH_TERMS:
        args={"keyword":keyword,"location":"United States","posted_date":"ONE","employment_types":["FULLTIME"],"jobs_per_page":jobs_per_page,"page_number":1}
        payload=call_tool(ENDPOINT,"search_jobs",args);rows=rows_from_payload(payload)
        for row in rows:
            job=_normalize(row);dedup[job["external_id"]]=job
        print(f"Dice / {keyword}: {len(rows)} results",flush=True)
    return list(dedup.values())
