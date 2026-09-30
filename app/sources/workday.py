from __future__ import annotations
import json
import re
import time
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.request import Request, urlopen
from pathlib import Path

# Workday discovery must maximize recall. An empty searchText traverses the
# employer's public board instead of relying on a finite vocabulary of titles.
SEARCH_TERMS = ("",)
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
    path=_cache_path(tenant,site);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(cache,indent=2),encoding="utf-8");tmp.replace(path)

def _json(url:str,timeout:int=20,body:dict|None=None,retries:int=3)->dict:
    data=json.dumps(body).encode("utf-8") if body is not None else None;last_error=None
    for attempt in range(retries):
        try:
            req=Request(url,data=data,headers={"Accept":"application/json","Content-Type":"application/json","Accept-Language":"en-US","User-Agent":"AI-Job-Search-Agent/0.9"})
            with urlopen(req,timeout=timeout) as resp:return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last_error=exc
            if attempt+1<retries:time.sleep(1.5*(2**attempt))
    raise last_error or RuntimeError("Workday request failed")

def job_detail_is_live(host:str,tenant:str,site:str,external_path:str,timeout:int=20)->tuple[bool,dict|None]:
    if not external_path:return False,None
    base=f"https://{host.strip('/')}/wday/cxs/{tenant}/{site}"
    try:payload=_json(f"{base}{external_path}",timeout,retries=2)
    except Exception:return False,None
    detail=payload.get("jobPostingInfo") or payload
    description=_plain(detail.get("jobDescription")) if isinstance(detail,dict) else "";title=(detail.get("title") or "") if isinstance(detail,dict) else ""
    return bool(title.strip() and description.strip()),detail if isinstance(detail,dict) else None

def _plain(value):
    text=unescape(value or "");text=re.sub(r"<[^>]+>"," ",text);return re.sub(r"\s+"," ",text).strip()

def _posted_at(value):
    text=(value or "").strip().lower();now=datetime.now(timezone.utc)
    if text in {"posted today","today"}:return now.isoformat()
    if text in {"posted yesterday","yesterday"}:return (now-timedelta(days=1)).isoformat()
    match=re.search(r"posted\s+(\d+)\s+days?\s+ago",text)
    if match:return (now-timedelta(days=int(match.group(1)))).isoformat()
    return None

def fetch_jobs(company:str,host:str,tenant:str,site:str,locale:str="en-US",timeout:int=20,hours:int=24,max_pages_per_term:int|None=None)->list[dict]:
    """Fetch the public Workday board broadly to exhaustion/freshness frontier.

    No source-level job-family filter is applied. Central qualification decides
    Data Engineer / Data Engineering / Analytics Engineering / Data Platform and
    all other eligibility rules after discovery. max_pages_per_term is only an
    explicit emergency safety override and is reported as TRUNCATED when reached.
    """
    origin=f"https://{host.strip('/')}";base=f"{origin}/wday/cxs/{tenant}/{site}";limit=20
    listing_count=candidate_count=duplicate_candidate_count=detail_failure_count=0
    pages_total=0;truncated_terms=[];out_by_path={};tenant_cache=_load_cache(tenant,site);incremental=bool(tenant_cache)
    previous_global=set(tenant_cache.get("_global_paths") or [])
    if not previous_global:
        for key,value in tenant_cache.items():
            if key.startswith("_") or not isinstance(value,dict):continue
            previous_global.update(value.get("paths") or [])
    current_global=[]
    for search_term in SEARCH_TERMS:
        offset=0;pages_scanned=0;total=None;cache_key=search_term or "__all__"
        while True:
            if max_pages_per_term is not None and pages_scanned>=max_pages_per_term:
                truncated_terms.append(cache_key);break
            payload=_json(f"{base}/jobs",timeout,{"appliedFacets":{},"limit":limit,"offset":offset,"searchText":search_term})
            if total is None:
                try:total=int(payload.get("total") or 0)
                except Exception:total=0
            rows=payload.get("jobPostings") or [];pages_scanned+=1;pages_total+=1
            if incremental:
                term_cache=tenant_cache.setdefault(cache_key,{});previous=set(term_cache.get("paths") or [])
                current=[row.get("externalPath") for row in rows if row.get("externalPath")];known_frontier=previous_global or previous
                if current and known_frontier and all(x in known_frontier for x in current):break
                seen_this_run=term_cache.setdefault("_current_paths",[]);seen_this_run.extend(x for x in current if x not in seen_this_run)
                current_global.extend(x for x in current if x not in current_global);term_cache["checked_at"]=datetime.now(timezone.utc).isoformat()
            if not rows:break
            listing_count+=len(rows)
            for row in rows:
                posted=_posted_at(row.get("postedOn"))
                if posted:
                    try:
                        if (datetime.now(timezone.utc)-datetime.fromisoformat(posted)).total_seconds()/3600>hours:continue
                    except Exception:pass
                candidate_count+=1;external_path=row.get("externalPath") or ""
                if not external_path:detail_failure_count+=1;continue
                if external_path in out_by_path:duplicate_candidate_count+=1;continue
                try:
                    detail_payload=_json(f"{base}{external_path}",timeout);detail=detail_payload.get("jobPostingInfo") or detail_payload
                except Exception:detail_failure_count+=1;continue
                description=_plain(detail.get("jobDescription"))
                if not description:detail_failure_count+=1;continue
                req_id=detail.get("jobReqId") or detail.get("jobPostingId") or external_path.rsplit("_",1)[-1]
                title=detail.get("title") or row.get("title") or "";location=detail.get("location") or row.get("locationsText");additional=detail.get("additionalLocations") or []
                if additional:location=" | ".join([location]+[str(x) for x in additional if x]) if location else " | ".join(map(str,additional))
                out_by_path[external_path]={"external_id":f"workday:{tenant}:{site}:{req_id}","source":"workday","company_key":company,"title":title,"location":location,"employment_type":detail.get("timeType"),"url":f"{origin}/{locale}/{site}{external_path}","description":description,"updated_at":posted,"posted_on":row.get("postedOn")}
            offset+=len(rows)
            parsed=[_posted_at(row.get("postedOn")) for row in rows];known=[datetime.fromisoformat(x) for x in parsed if x]
            if known and max(known)<datetime.now(timezone.utc)-timedelta(hours=hours):break
            if len(rows)<limit or (total and offset>=total):break
    if incremental:
        for key,term_cache in list(tenant_cache.items()):
            if key.startswith("_") or not isinstance(term_cache,dict):continue
            current=term_cache.pop("_current_paths",[])
            if current:
                prior=term_cache.get("paths") or [];term_cache["paths"]=list(dict.fromkeys(current+prior))[:2000]
        tenant_cache["_global_paths"]=list(dict.fromkeys(current_global+list(previous_global)))[:5000];tenant_cache["_global_checked_at"]=datetime.now(timezone.utc).isoformat();_save_cache(tenant,site,tenant_cache)
    out=list(out_by_path.values());unique_candidates=len(out)+detail_failure_count
    state="TRUNCATED" if truncated_terms else "EXHAUSTED_OR_FRESHNESS_FRONTIER"
    print(f"Workday / {company}: {listing_count} board rows, {pages_total} pages, {unique_candidates} fresh/unknown-date candidates, {len(out)} detailed JDs, pagination={state}"+(f", truncated_terms={len(truncated_terms)}" if truncated_terms else "")+(f", {detail_failure_count} detail failures" if detail_failure_count else "")+(f", {duplicate_candidate_count} duplicate hits" if duplicate_candidate_count else ""),flush=True)
    return out
