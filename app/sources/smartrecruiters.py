from __future__ import annotations
import json
import re
from pathlib import Path
from html import unescape
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

BASE = "https://api.smartrecruiters.com/v1/companies"
ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "generated" / "smartrecruiters_cache"

def _cache_path(company_identifier: str) -> Path:
    safe=re.sub(r"[^A-Za-z0-9_.-]+","_",company_identifier)
    return CACHE_DIR / f"{safe}.json"

def _load_cache(company_identifier: str) -> dict:
    path=_cache_path(company_identifier)
    if not path.exists():return {}
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def _save_cache(company_identifier: str, payload: dict) -> None:
    path=_cache_path(company_identifier);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(payload,indent=2),encoding="utf-8");tmp.replace(path)

def _get_json(url: str, timeout: int) -> dict:
    req=Request(url,headers={"Accept":"application/json","User-Agent":"AI-Job-Search-Agent/0.5"})
    with urlopen(req,timeout=timeout) as resp:return json.loads(resp.read().decode("utf-8"))

def _plain(value: str | None) -> str:
    text=unescape(value or "");text=re.sub(r"<[^>]+>"," ",text);return re.sub(r"\s+"," ",text).strip()

def _location(loc: dict) -> str | None:
    parts=[loc.get("city"),loc.get("region"),loc.get("country")];value=", ".join(str(x) for x in parts if x)
    if loc.get("remote"):return f"Remote | {value}" if value else "Remote"
    return value or None

def fetch_jobs(company_identifier: str, timeout: int = 12, hours: int = 24) -> list[dict]:
    """Fetch all fresh/unknown-date public SmartRecruiters postings for a company.

    Discovery no longer applies a title-family gate. The downstream qualification
    stage owns Data Engineering / Analytics Engineering / Data Platform semantics.
    The source adapter only uses authoritative listing freshness to avoid re-fetching
    demonstrably old pages during incremental cycles.
    """
    out=[];offset=0;limit=100;listing_count=0;detail_count=0
    incremental=hours<=2;cache=_load_cache(company_identifier) if incremental else {};previous_ids=set(cache.get("posting_ids") or []);current_ids=[]
    cutoff=datetime.now(timezone.utc)-timedelta(hours=hours)
    def recent(row):
        raw=row.get("releasedDate")
        if not raw:return True
        try:return datetime.fromisoformat(raw.replace("Z","+00:00")).astimezone(timezone.utc)>=cutoff
        except Exception:return True
    while True:
        url=f"{BASE}/{company_identifier}/postings?{urlencode({'limit':limit,'offset':offset})}"
        payload=_get_json(url,timeout);rows=payload.get("content") or []
        page_ids=[str(row.get("uuid") or row.get("id") or "") for row in rows];page_ids=[x for x in page_ids if x]
        if incremental and rows and page_ids and all(x in previous_ids for x in page_ids):break
        listing_count+=len(rows);current_ids.extend(page_ids);recent_rows=[row for row in rows if recent(row)]
        for row in recent_rows:
            posting_id=row.get("uuid") or row.get("id")
            if not posting_id:continue
            detail_url=f"{BASE}/{company_identifier}/postings/{posting_id}"
            try:detail=_get_json(detail_url,timeout)
            except Exception:detail=row
            job_ad=detail.get("jobAd") or {};description=" ".join(_plain(x) for x in [job_ad.get("companyDescription"),job_ad.get("jobDescription"),job_ad.get("qualifications"),job_ad.get("additionalInformation")] if x)
            company=detail.get("company") or row.get("company") or {};loc=detail.get("location") or row.get("location") or {};employment=detail.get("typeOfEmployment") or row.get("typeOfEmployment") or {}
            out.append({"external_id":f"smartrecruiters:{company_identifier}:{posting_id}","source":"smartrecruiters","company_key":company.get("name") or company_identifier,"title":detail.get("name") or row.get("name") or "","location":_location(loc),"employment_type":employment.get("label"),"url":detail.get("postingUrl") or detail.get("applyUrl") or row.get("ref"),"description":description,"description_complete":bool(description.strip()),"updated_at":detail.get("releasedDate") or row.get("releasedDate")})
            detail_count+=1
        offset+=len(rows);total=int(payload.get("totalFound") or 0)
        if rows and not recent_rows:break
        if not rows or offset>=total:break
    if incremental:
        merged=list(dict.fromkeys(current_ids+list(previous_ids)))[:5000];_save_cache(company_identifier,{"posting_ids":merged})
    print(f"SmartRecruiters / {company_identifier}: {listing_count} rows scanned ({hours}h window), {detail_count} fresh/unknown-date postings collected; job-family filtering deferred downstream",flush=True)
    return out
