from __future__ import annotations
import json
import re
import time
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.request import Request, urlopen
from pathlib import Path

SEARCH_TERMS = ("Data Engineer", "Senior Data Engineer", "Sr Data Engineer", "Sr. Data Engineer", "Lead Data Engineer", "Staff Data Engineer", "Principal Data Engineer", "AWS Data Engineer", "Azure Data Engineer", "Cloud Data Engineer", "Spark Data Engineer", "PySpark Data Engineer", "Python Data Engineer", "ETL Data Engineer", "Big Data Engineer", "Data Platform Engineer", "Data Infrastructure Engineer", "Data Pipeline Engineer", "Data Analytics Engineer", "Data Integration Engineer", "Analytics Engineer")
ROOT=Path(__file__).resolve().parents[2]
CACHE_DIR=ROOT/"generated"/"workday_cache"

def _cache_path(tenant,site):
    safe=re.sub(r"[^A-Za-z0-9_.-]+","_",f"{tenant}__{site}")
    return CACHE_DIR/f"{safe}.json"

def _load_cache(tenant,site):
    path=_cache_path(tenant,site)
    if not path.exists(): return {}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}

def _save_cache(tenant,site,cache):
    path=_cache_path(tenant,site)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache,indent=2),encoding="utf-8")
    tmp.replace(path)

DE_TITLE_PATTERNS = (
    "data engineer",
    "data platform engineer",
    "data infrastructure engineer",
    "data pipeline engineer",
    "big data engineer",
    "cloud data engineer",
    "aws data engineer",
    "azure data engineer",
    "data analytics engineer",
    "data integration engineer",
    "analytics engineer",
)


def _json(url: str, timeout: int = 20, body: dict | None = None, retries: int = 3) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, data=data, headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Accept-Language": "en-US",
                "User-Agent": "AI-Job-Search-Agent/0.7",
            })
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (2 ** attempt))
    raise last_error or RuntimeError("Workday request failed")


def _plain(value: str | None) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_de_title(title: str | None) -> bool:
    value = re.sub(r"\s+", " ", (title or "").lower()).strip()
    return any(x in value for x in DE_TITLE_PATTERNS)


def _posted_at(value: str | None) -> str | None:
    text = (value or "").strip().lower()
    now = datetime.now(timezone.utc)
    if text in {"posted today", "today"}:
        return now.isoformat()
    if text in {"posted yesterday", "yesterday"}:
        return (now - timedelta(days=1)).isoformat()
    match = re.search(r"posted\s+(\d+)\s+days?\s+ago", text)
    if match:
        return (now - timedelta(days=int(match.group(1)))).isoformat()
    return None


def fetch_jobs(company: str, host: str, tenant: str, site: str, locale: str = "en-US", timeout: int = 20, hours: int = 24) -> list[dict]:
    """Fetch Data Engineer-family jobs from one public Workday CXS career site.

    Workday calls are retried with exponential backoff so transient DNS/network
    issues do not unnecessarily reduce hourly discovery coverage.
    """
    origin = f"https://{host.strip('/')}"
    base = f"{origin}/wday/cxs/{tenant}/{site}"
    limit = 20
    listing_count = 0
    candidate_count = 0
    out_by_path: dict[str,dict] = {}
    # One cache file per tenant/site avoids lost updates because Workday tenants are
    # scanned concurrently by discovery.py.
    tenant_cache=_load_cache(tenant,site)
    incremental=hours<=2

    for search_term in SEARCH_TERMS:
      offset = 0
      total: int | None = None
      while True:
        payload = _json(f"{base}/jobs", timeout, {
            "appliedFacets": {}, "limit": limit, "offset": offset, "searchText": search_term
        })
        if total is None:
            try: total = int(payload.get("total") or 0)
            except Exception: total = 0
        rows = payload.get("jobPostings") or []
        if incremental:
            term_cache=tenant_cache.setdefault(search_term,{})
            previous=set(term_cache.get("paths") or [])
            current=[row.get("externalPath") for row in rows if row.get("externalPath")]
            # Compare against the cache from the PREVIOUS completed run. Do not add
            # pages to the stop-set while traversing the current run, otherwise the
            # cache cannot form a stable cross-run frontier.
            if current and all(x in previous for x in current):
                break
            seen_this_run=term_cache.setdefault("_current_paths",[])
            seen_this_run.extend(x for x in current if x not in seen_this_run)
            term_cache["checked_at"]=datetime.now(timezone.utc).isoformat()
        if not rows:
            break
        listing_count += len(rows)

        for row in rows:
            posted=_posted_at(row.get("postedOn"))
            if posted:
                try:
                    age_hours=(datetime.now(timezone.utc)-datetime.fromisoformat(posted)).total_seconds()/3600
                    if age_hours>hours: continue
                except Exception: pass
            if not _is_de_title(row.get("title")):
                continue
            candidate_count += 1
            external_path = row.get("externalPath") or ""
            if not external_path:
                continue
            try:
                detail_payload = _json(f"{base}{external_path}", timeout)
                detail = detail_payload.get("jobPostingInfo") or detail_payload
            except Exception:
                detail = {}

            req_id = detail.get("jobReqId") or detail.get("jobPostingId") or external_path.rsplit("_", 1)[-1]
            title = detail.get("title") or row.get("title") or ""
            location = detail.get("location") or row.get("locationsText")
            additional = detail.get("additionalLocations") or []
            if additional:
                location = " | ".join([location] + [str(x) for x in additional if x]) if location else " | ".join(map(str, additional))
            public_url = f"{origin}/{locale}/{site}{external_path}"
            out_by_path[external_path]={
                "external_id": f"workday:{tenant}:{site}:{req_id}",
                "source": "workday",
                "company_key": company,
                "title": title,
                "location": location,
                "employment_type": detail.get("timeType"),
                "url": public_url,
                "description": _plain(detail.get("jobDescription")),
                "updated_at": posted,
                "posted_on": row.get("postedOn"),
            }

        offset += len(rows)
        # Workday search results are normally newest-first. Once a whole page is
        # explicitly older than this cycle window, stop traversing historical matches.
        parsed=[_posted_at(row.get("postedOn")) for row in rows]
        known=[datetime.fromisoformat(x) for x in parsed if x]
        if known and len(known)==len(rows):
            cutoff=datetime.now(timezone.utc)-timedelta(hours=hours)
            if max(known) < cutoff:
                break
        if len(rows) < limit or (total and offset >= total):
            break

    if incremental:
        for term_cache in tenant_cache.values():
            current=term_cache.pop("_current_paths",[])
            if current:
                prior=term_cache.get("paths") or []
                term_cache["paths"]=list(dict.fromkeys(current+prior))[:2000]
        _save_cache(tenant,site,tenant_cache)
    out=list(out_by_path.values())
    print(f"Workday / {company}: {listing_count} targeted search results ({hours}h window), {candidate_count} DE candidates, {len(out)} detailed JDs", flush=True)
    return out
