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
    for href in re.findall(r'href=["\']([^"\']*?/job-openings/[^"\']+)["\']',page,re.I):
        url=parse.urljoin(BASE,html.unescape(href))
        if url not in links: links.append(url)
    return links

def _next_search_links(page: str, current_url: str) -> list[str]:
    """Return same-host Monster search pagination links exposed by the page."""
    out=[]
    for href in re.findall(r'href=["\']([^"\']+)["\']',page,re.I):
        url=parse.urljoin(current_url,html.unescape(href));parts=parse.urlsplit(url)
        if parts.netloc.lower() not in {"monster.com","www.monster.com"}:continue
        low=url.lower()
        if ("/jobs/" in low or "/jobs/q-" in low) and (re.search(r"[?&](?:page|p|offset)=\d+",low) or re.search(r"/page/\d+",low)):
            if url not in out:out.append(url)
    return out

def _jsonld(page: str) -> dict:
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',page,re.I|re.S):
        try:obj=json.loads(html.unescape(raw).strip())
        except Exception:continue
        items=obj if isinstance(obj,list) else [obj]
        for item in items:
            if isinstance(item,dict) and item.get("@type")=="JobPosting":return item
            if isinstance(item,dict) and isinstance(item.get("@graph"),list):
                for child in item["@graph"]:
                    if isinstance(child,dict) and child.get("@type")=="JobPosting":return child
    return {}

def _location(value):
    vals=value if isinstance(value,list) else [value];out=[]
    for v in vals:
        if not isinstance(v,dict):continue
        a=v.get("address") or {}
        if isinstance(a,dict):
            text=", ".join(str(a.get(k)) for k in ("addressLocality","addressRegion","addressCountry") if a.get(k))
            if text:out.append(text)
    return " / ".join(out)

def _normalize(url: str, data: dict) -> dict:
    org=data.get("hiringOrganization") or {};desc=re.sub(r"<[^>]+>"," ",str(data.get("description") or ""));desc=html.unescape(re.sub(r"\s+"," ",desc)).strip();raw_id=data.get("identifier")
    if isinstance(raw_id,dict):raw_id=raw_id.get("value")
    stable=hashlib.sha1(str(raw_id or url).encode()).hexdigest()[:20];posted=data.get("datePosted")
    return {"external_id":f"monster:{stable}","source":"monster","company_key":org.get("name") if isinstance(org,dict) else "Unknown","title":data.get("title") or "","location":_location(data.get("jobLocation")),"employment_type":data.get("employmentType") or "","url":url,"description":desc,"description_complete":bool(len(desc)>=1200),"description_length":len(desc),"updated_at":posted,"posted_on":posted,"provider_us_scoped":True}

def fetch_jobs(hours: int=24, max_jobs_per_term: int|None=None, max_search_pages_per_term: int|None=None) -> list[dict]:
    """Crawl Monster search results to the visible pagination frontier.

    There is no implicit 40-job ceiling. Optional limits are emergency safeguards
    only and truncation is reported explicitly. Downstream central filters remain
    responsible for final job-family/eligibility decisions.
    """
    dedup={};truncated=[];total_search_pages=0
    for keyword in SEARCH_TERMS:
        q=parse.quote_plus(keyword);start=f"{BASE}/jobs/q-{q.replace('+','-').lower()}-jobs";queue=[start];seen_pages=set();links=[];seen_links=set()
        while queue:
            if max_search_pages_per_term is not None and len(seen_pages)>=max_search_pages_per_term:
                truncated.append(f"{keyword}:search_pages");break
            page_url=queue.pop(0)
            if page_url in seen_pages:continue
            try:page=_get(page_url)
            except Exception:continue
            seen_pages.add(page_url);total_search_pages+=1
            for url in _job_links(page):
                if url not in seen_links:
                    seen_links.add(url);links.append(url)
                    if max_jobs_per_term is not None and len(links)>=max_jobs_per_term:
                        truncated.append(f"{keyword}:jobs");break
            if max_jobs_per_term is not None and len(links)>=max_jobs_per_term:break
            for nxt in _next_search_links(page,page_url):
                if nxt not in seen_pages and nxt not in queue:queue.append(nxt)
        count=0
        for url in links:
            try:
                data=_jsonld(_get(url))
                if not data:continue
                job=_normalize(url,data)
                if job["title"]:dedup[job["external_id"]]=job;count+=1
            except Exception:continue
        print(f"Monster / {keyword}: {count} detailed results from {len(seen_pages)} search page(s), {len(links)} detail link(s)",flush=True)
    state="TRUNCATED" if truncated else "EXHAUSTED_OR_FRONTIER"
    print(f"Monster: {len(dedup)} unique jobs across {total_search_pages} search page(s), pagination={state}"+(f", truncations={len(truncated)}" if truncated else ""),flush=True)
    return list(dedup.values())
