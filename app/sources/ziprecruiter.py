from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from app.sources.mcp_jobs import call_tool, rows_from_payload

ENDPOINT = "https://api.ziprecruiter.com/mcp"
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
    url = row.get("url") or row.get("job_url") or row.get("jobUrl") or row.get("apply_url") or ""
    raw_id = row.get("id") or row.get("job_id") or row.get("jobId") or url or f"{row.get('company')}:{row.get('title')}:{row.get('posted_at')}"
    stable = hashlib.sha1(str(raw_id).encode("utf-8")).hexdigest()[:20]
    location = row.get("location") or row.get("job_location")
    if isinstance(location, dict):
        location = ", ".join(str(location.get(k)) for k in ("city", "state", "country") if location.get(k))
    return {
        "external_id": f"ziprecruiter:{stable}",
        "source": "ziprecruiter",
        "company_key": row.get("company") or row.get("company_name") or row.get("companyName") or "Unknown",
        "title": row.get("title") or row.get("job_title") or row.get("jobTitle") or "",
        "location": location,
        "employment_type": row.get("employment_type") or row.get("employmentType") or "Full-Time",
        "url": url,
        "description": row.get("description") or row.get("summary") or row.get("snippet") or "",
        "updated_at": _iso(row.get("posted_at") or row.get("postedDate") or row.get("date_posted") or row.get("datePosted")),
        "posted_on": row.get("posted_at") or row.get("postedDate") or row.get("date_posted"),
    }


def fetch_jobs() -> list[dict]:
    """Search ZipRecruiter's official MCP with native US/full-time/recency filters."""
    dedup = {}
    for keyword in SEARCH_TERMS:
        # The official server supports country, recency, employment type and offset.
        # Use a one-day recency request and let our strict freshness gate verify the
        # returned posting timestamp again before a job can qualify.
        args = {
            "keyword": keyword,
            "country": "US",
            "recency": 1,
            "employment_type": "full_time",
            "offset": 0,
        }
        payload = call_tool(ENDPOINT, "search_jobs", args)
        rows = rows_from_payload(payload)
        for row in rows:
            job = _normalize(row)
            dedup[job["external_id"]] = job
        print(f"ZipRecruiter / {keyword}: {len(rows)} results", flush=True)
    return list(dedup.values())
