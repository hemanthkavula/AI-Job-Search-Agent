from __future__ import annotations
import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode

BASE = "https://api.lever.co/v0/postings"

def _get(url: str, timeout: int):
    req=Request(url,headers={"Accept":"application/json","User-Agent":"AI-Job-Search-Agent/0.3"})
    with urlopen(req,timeout=timeout) as resp:return json.loads(resp.read().decode("utf-8"))

def fetch_jobs(site: str, timeout: int = 20, page_size: int = 100, max_pages: int | None = None) -> list[dict]:
    """Fetch the complete public Lever board, following skip/limit pages to exhaustion.

    max_pages is an explicit emergency safeguard only. If supplied and reached, the
    adapter reports TRUNCATED instead of silently presenting a partial board as complete.
    """
    out=[];seen=set();skip=0;pages=0;truncated=False
    while True:
        if max_pages is not None and pages>=max_pages:
            truncated=True;break
        url=f"{BASE}/{site}?{urlencode({'mode':'json','limit':page_size,'skip':skip})}"
        payload=_get(url,timeout);pages+=1
        if not isinstance(payload,list) or not payload:break
        new_rows=0
        for j in payload:
            jid=j.get("id") or j.get("hostedUrl") or j.get("applyUrl")
            if not jid or jid in seen:continue
            seen.add(jid);new_rows+=1
            lists=j.get("lists") or []
            description=" ".join([j.get("descriptionPlain") or "",j.get("additionalPlain") or ""]+[x.get("content","") for x in lists])
            cats=j.get("categories") or {};job_url=j.get("hostedUrl") or j.get("applyUrl")
            out.append({"external_id":f"lever:{site}:{jid}","source":"lever","company_key":site,"title":j.get("text","") ,"location":cats.get("location"),"url":job_url,"original_url":job_url,"ats_provider":"lever","ats_identifier":site,"job_id":j.get("id"),"requisition_id":j.get("id"),"description":description,"description_complete":bool(description.strip()),"updated_at":None})
        # A short page is the normal terminal frontier. No-new-IDs also protects
        # against providers/proxies that ignore skip and repeat the first page.
        if len(payload)<page_size or new_rows==0:break
        skip+=len(payload)
    state="TRUNCATED" if truncated else "EXHAUSTED"
    print(f"Lever / {site}: {len(out)} live postings from {pages} page(s), pagination={state}",flush=True)
    return out
