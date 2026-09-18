from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib import request
from app.sources.mcp_jobs import call_tool, rows_from_payload

ENDPOINT = "https://mcp.dice.com/mcp"
# Dice keyword search already matches seniority/technology prefixes around the
# core phrase, so dozens of near-identical queries mostly return the same jobs.
# Keep broad family roots; final title/JD eligibility decides whether a posting
# is truly Data Engineering.
SEARCH_TERMS = (
    "Data Engineer",
    "Data Engineering",
    "Data Platform Engineer",
    "Data Infrastructure Engineer",
    "Data Pipeline Engineer",
    "Data Integration Engineer",
    "Analytics Engineer",
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
    # Discovery intentionally keeps the MCP summary lightweight. Complete JD
    # resolution happens only after this job passes eligibility filters.
    workplace=row.get("workplaceTypes") or row.get("workplaceType") or row.get("workplace_types")
    return {
        "external_id":f"dice:{stable}","source":"dice","company_key":row.get("companyName") or row.get("company") or "Unknown",
        "title":row.get("title") or row.get("jobTitle") or "","location":location,
        "employment_type":row.get("employmentType") or row.get("employment_type") or "FULLTIME","workplace_type":workplace,
        "url":url,"company_url":row.get("companyPageUrl") or "","description":description,
        "description_complete":bool(description and len(description.strip()) >= 1200),
        "description_length":len(description.strip()),
        "updated_at":_iso(row.get("postedDate") or row.get("posted_at") or row.get("datePosted")),
        "posted_on":row.get("postedDate") or row.get("datePosted"),
        "sponsorship_signal":row.get("willingToSponsor") if "willingToSponsor" in row else row.get("willing_to_sponsor"),
        "provider_us_scoped":True,"provider_fulltime_scoped":True,
    }

def fetch_jobs(jobs_per_page: int = 100, search_terms=None, hours: int = 24) -> list[dict]:
    """Search Dice MCP for source-filtered candidates. Short summaries remain incomplete until a later full-JD resolver stage."""
    dedup={}
    for keyword in (search_terms or SEARCH_TERMS):
        # Dice exposes a one-day server-side posting filter, not an hourly one.
        # Hour-level freshness remains enforced centrally from postedDate.
        args={"keyword":keyword,"location":"United States","posted_date":"ONE","jobs_per_page":jobs_per_page,"page_number":1}
        payload=call_tool(ENDPOINT,"search_jobs",args);rows=rows_from_payload(payload)
        for row in rows:
            job=_normalize(row);dedup[job["external_id"]]=job
        print(f"Dice / {keyword}: {len(rows)} results",flush=True)
    return list(dedup.values())
