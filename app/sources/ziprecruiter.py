from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from app.sources.mcp_jobs import call_tool, rows_from_payload

ENDPOINT = "https://api.ziprecruiter.com/mcp"
SEARCH_TERMS = (
    "Data Engineer",
    "Senior Data Engineer",
    "Sr Data Engineer",
    "Sr. Data Engineer",
    "Lead Data Engineer",
    "Staff Data Engineer",
    "Principal Data Engineer",
    "AWS Data Engineer",
    "Azure Data Engineer",
    "Cloud Data Engineer",
    "Spark Data Engineer",
    "PySpark Data Engineer",
    "Python Data Engineer",
    "Big Data Engineer",
    "Data Platform Engineer",
    "Data Infrastructure Engineer",
    "Data Pipeline Engineer",
    "Data Integration Engineer",
    "Analytics Engineer",
    "ETL Engineer",
)
PAGE_SIZE = 5


def _iso(value):
    if not value:return None
    text=str(value).strip()
    try:return datetime.fromisoformat(text.replace("Z","+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:return text


def _normalize(row: dict) -> dict:
    url=row.get("url") or row.get("job_url") or row.get("jobUrl") or row.get("apply_url") or ""
    raw_id=row.get("id") or row.get("job_id") or row.get("jobId") or url or f"{row.get('company')}:{row.get('title')}:{row.get('posted_at')}"
    stable=hashlib.sha1(str(raw_id).encode("utf-8")).hexdigest()[:20]
    location=row.get("location") or row.get("job_location")
    if isinstance(location,dict):location=", ".join(str(location.get(k)) for k in ("city","state","country") if location.get(k))
    description=row.get("description") or row.get("summary") or row.get("snippet") or ""
    return {"external_id":f"ziprecruiter:{stable}","source":"ziprecruiter","company_key":row.get("company") or row.get("company_name") or row.get("companyName") or "Unknown","title":row.get("title") or row.get("job_title") or row.get("jobTitle") or "","location":location,"employment_type":row.get("employment_type") or row.get("employmentType") or "Full-Time","url":url,"description":description,"description_complete":bool(description and len(description.strip())>=1200),"updated_at":_iso(row.get("posted_at") or row.get("postedDate") or row.get("date_posted") or row.get("datePosted")),"posted_on":row.get("posted_at") or row.get("postedDate") or row.get("date_posted") or row.get("datePosted")}


def fetch_jobs(max_pages_per_term: int | None = None) -> list[dict]:
    """Search ZipRecruiter's official MCP to the available pagination frontier.

    The prior adapter hard-coded offsets 0 and 5, limiting each query to at most ten
    rows. We now continue offset pagination until an empty/short/repeated page.
    max_pages_per_term is an explicit emergency safeguard and is reported as truncation.
    """
    dedup={};total_pages=0;truncated_terms=[]
    for keyword in SEARCH_TERMS:
        offset=0;page=0;term_seen=set();term_total=0
        while True:
            if max_pages_per_term is not None and page>=max_pages_per_term:
                truncated_terms.append(keyword);break
            args={"keyword":keyword,"country":"US","recency":1,"employment_type":"full_time","offset":offset}
            payload=call_tool(ENDPOINT,"search_jobs",args);rows=rows_from_payload(payload);page+=1;total_pages+=1
            if not rows:break
            new_ids=0
            for row in rows:
                job=_normalize(row);jid=job["external_id"]
                if jid not in term_seen:term_seen.add(jid);new_ids+=1
                dedup[jid]=job
            term_total+=len(rows)
            print(f"ZipRecruiter / {keyword} / offset {offset}: {len(rows)} results, {new_ids} new",flush=True)
            if len(rows)<PAGE_SIZE or new_ids==0:break
            offset+=len(rows)
        print(f"ZipRecruiter / {keyword}: {term_total} rows scanned",flush=True)
    state="TRUNCATED" if truncated_terms else "EXHAUSTED_OR_FRONTIER"
    print(f"ZipRecruiter: {len(dedup)} unique jobs across {total_pages} page request(s), pagination={state}"+(f", truncated_terms={len(truncated_terms)}" if truncated_terms else ""),flush=True)
    return list(dedup.values())
