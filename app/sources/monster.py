from __future__ import annotations

import hashlib, html, json, re
from datetime import datetime, timezone
from urllib import parse, request

SEARCH_TERMS=("Data Engineer","Data Engineering","Data Platform Engineer","Data Infrastructure Engineer","Data Pipeline Engineer","Data Integration Engineer","Analytics Engineer")
BASE="https://www.monster.com"

def _get(url: str) -> str:
    req=request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; AI-Job-Search-Agent/1.0)"})
    with request.urlopen(req,timeout=25) as r:
        return r.read().decode("utf-8","ignore")

def _job_links(page: str) -> list[str]:
    links=[]
    for href in re.findall(r'href=["\']([^"\']+/job-openings/[^"\']+)["\']',page,re.I):
        url=parse.urljoin(BASE,html.unescape(href))
        if url not in links: links.append(url)
    return links

def _jsonld(page: str) -> dict:
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',page,re.I|re.S):
        try:
            obj=json.loads(html.unescape(raw).strip())
        except Exception:
            continue
        items=obj if isinstance(obj,list) else [obj]
        for item in items:
            if isinstance(item,dict) and item.get("@type")=="JobPosting": return item
            if isinstance(item,dict) and isinstance(item.get("@graph"),list):
                for child in item["@graph"]:
                    if isinstance(child,dict) and child.get("@type")=="JobPosting": return child
    return {}

def _location(value):
    vals=value if isinstance(value,list) else [value]
    out=[]
    for v in vals:
        if not isinstance(v,dict): continue
        a=v.get("address") or {}
        if isinstance(a,dict):
            text=", ".join(str(a.get(k)) for k in ("addressLocality","addressRegion","addressCountry") if a.get(k))
            if text: out.append(text)
    return " / ".join(out)

def _normalize(url: str, data: dict) -> dict:
    org=data.get("hiringOrganization") or {}
    desc=re.sub(r"<[^>]+>"," ",str(data.get("description") or ""))
    desc=html.unescape(re.sub(r"\s+"," ",desc)).strip()
    raw_id=data.get("identifier")
    if isinstance(raw_id,dict): raw_id=raw_id.get("value")
    stable=hashlib.sha1(str(raw_id or url).encode()).hexdigest()[:20]
    posted=data.get("datePosted")
    return {"external_id":f"monster:{stable}","source":"monster","company_key":org.get("name") if isinstance(org,dict) else "Unknown",
            "title":data.get("title") or "","location":_location(data.get("jobLocation")),
            "employment_type":data.get("employmentType") or "","url":url,"description":desc,
            "description_complete":bool(len(desc)>=1200),"description_length":len(desc),
            "updated_at":posted,"posted_on":posted,"provider_us_scoped":True}

def fetch_jobs(hours: int=24, max_jobs_per_term: int=40) -> list[dict]:
    dedup={}
    for keyword in SEARCH_TERMS:
        q=parse.quote_plus(keyword)
        page=_get(f"{BASE}/jobs/q-{q.replace('+','-').lower()}-jobs")
        links=_job_links(page)[:max_jobs_per_term]
        count=0
        for url in links:
            try:
                data=_jsonld(_get(url))
                if not data: continue
                job=_normalize(url,data)
                if job["title"]:
                    dedup[job["external_id"]]=job;count+=1
            except Exception:
                continue
        print(f"Monster / {keyword}: {count} detailed results",flush=True)
    return list(dedup.values())
