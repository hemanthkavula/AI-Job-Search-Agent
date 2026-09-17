from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from app.sources.mcp_jobs import call_tool, rows_from_payload

ENDPOINT = "https://mcp.dice.com/mcp"
SEARCH_TERMS = ("Data Engineer", "Senior Data Engineer", "Lead Data Engineer", "Data Platform Engineer", "Cloud Data Engineer")


def _iso(value):
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return text


def _normalize(row: dict) -> dict:
    url = row.get("detailsPageUrl") or row.get("url") or row.get("jobUrl") or ""
    raw_id = row.get("id") or row.get("jobId") or url or f"{row.get('companyName')}:{row.get('title')}:{row.get('postedDate')}"
    stable = hashlib.sha1(str(raw_id).encode("utf-8")).hexdigest()[:20]
    location = row.get("jobLocation") or row.get("location")
    if isinstance(location, dict):
        location = ", ".join(str(location.get(k)) for k in ("city", "state", "country") if location.get(k))
    return {
        "external_id": f"dice:{stable}",
        "source": "dice",
        "company_key": row.get("companyName") or row.get("company") or "Unknown",
        "title": row.get("title") or row.get("jobTitle") or "",
        "location": location,
        "employment_type": row.get("employmentType") or row.get("employment_type") or "FULLTIME",
        "url": url,
        "description": row.get("description") or row.get("summary") or row.get("jobDescription") or "",
        "updated_at": _iso(row.get("postedDate") or row.get("posted_at") or row.get("datePosted")),
        "posted_on": row.get("postedDate") or row.get("datePosted"),
        "sponsorship_signal": row.get("willingToSponsor") or row.get("willing_to_sponsor"),
    }


def fetch_jobs(jobs_per_page: int = 100) -> list[dict]:
    """Search Dice's official MCP for US full-time DE-family jobs posted in one day.

    We intentionally do not set willing_to_sponsor: unknown sponsorship must remain
    eligible under the candidate policy; explicit no-sponsorship language is handled
    later by the normal eligibility engine.
    """
    dedup = {}
    for keyword in SEARCH_TERMS:
        args = {
            "keyword": keyword,
            "location": "United States",
            "posted_date": "ONE",
            "employment_types": ["FULLTIME"],
            "jobs_per_page": jobs_per_page,
            "page_number": 1,
        }
        payload = call_tool(ENDPOINT, "search_jobs", args)
        rows = rows_from_payload(payload)
        for row in rows:
            job = _normalize(row)
            dedup[job["external_id"]] = job
        print(f"Dice / {keyword}: {len(rows)} results", flush=True)
    return list(dedup.values())
