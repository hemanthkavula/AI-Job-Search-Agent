from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from app.sources.mcp_jobs import call_tool, rows_from_payload

ENDPOINT = "https://mcp.dice.com/mcp"
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
    if isinstance(value,dict):return ", ".join(str(value.get(k)) for k in ("city","state","country") if value.get(k))
    return value

def _normalize(row: dict) -> dict:
    url=row.get("detailsPageUrl") or row.get("url") or row.get("jobUrl") or ""
    raw_id=row.get("id") or row.get("jobId") or url or f"{row.get('companyName')}:{row.get('title')}:{row.get('postedDate')}"
    stable=hashlib.sha1(str(raw_id).encode("utf-8")).hexdigest()[:20]
    location=_stringify_location(row.get("jobLocation") or row.get("location"));description=row.get("description") or row.get("jobDescription") or row.get("summary") or "";workplace=row.get("workplaceTypes") or row.get("workplaceType") or row.get("workplace_types")
    return {"external_id":f"dice:{stable}","source":"dice","company_key":row.get("companyName") or row.get("company") or "Unknown","title":row.get("title") or row.get("jobTitle") or "","location":location,"employment_type":row.get("employmentType") or row.get("employment_type") or "FULLTIME","workplace_type":workplace,"url":url,"company_url":row.get("companyPageUrl") or "","description":description,"description_complete":bool(description and len(description.strip())>=1200),"description_length":len(description.strip()),"updated_at":_iso(row.get("postedDate") or row.get("posted_at") or row.get("datePosted")),"posted_on":row.get("postedDate") or row.get("datePosted"),"sponsorship_signal":row.get("willingToSponsor") if "willingToSponsor" in row else row.get("willing_to_sponsor"),"provider_us_scoped":True,"provider_fulltime_scoped":True}

def fetch_jobs(jobs_per_page: int = 100, search_terms=None, hours: int = 24, max_pages_per_term: int | None = None) -> list[dict]:
    """Search Dice MCP across every available result page for each target-family query.

    The previous implementation requested page 1 only. Pagination now continues until
    an empty/short/repeated page frontier. max_pages_per_term is an explicit emergency
    safeguard and is reported as truncation when reached.
    """
    dedup={};total_pages=0;truncated_terms=[]
    for keyword in (search_terms or SEARCH_TERMS):
        page=1;term_seen=set();term_rows=0
        while True:
            if max_pages_per_term is not None and page>max_pages_per_term:
                truncated_terms.append(keyword);break
            args={"keyword":keyword,"location":"United States","posted_date":"ONE","jobs_per_page":jobs_per_page,"page_number":page}
            payload=call_tool(ENDPOINT,"search_jobs",args);rows=rows_from_payload(payload);total_pages+=1
            if not rows:break
            new_ids=0
            for row in rows:
                job=_normalize(row);jid=job["external_id"]
                if jid not in term_seen:term_seen.add(jid);new_ids+=1
                dedup[jid]=job
            term_rows+=len(rows)
            print(f"Dice / {keyword} / page {page}: {len(rows)} results, {new_ids} new",flush=True)
            if len(rows)<jobs_per_page or new_ids==0:break
            page+=1
    state="TRUNCATED" if truncated_terms else "EXHAUSTED_OR_FRONTIER"
    print(f"Dice: {len(dedup)} unique jobs across {total_pages} page request(s), pagination={state}"+(f", truncated_terms={len(truncated_terms)}" if truncated_terms else ""),flush=True)
    return list(dedup.values())
