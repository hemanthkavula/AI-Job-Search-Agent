from __future__ import annotations

import html, json, re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

UA={"User-Agent":"Mozilla/5.0","Accept":"text/html,application/json,*/*"}

def _get(url: str, timeout: int=25) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _plain(v) -> str:
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",html.unescape(str(v or "")))).strip()

def _postings(body: str) -> list[dict]:
    out=[]
    for raw in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',body,re.I|re.S):
        try:data=json.loads(html.unescape(raw.strip()))
        except Exception:continue
        stack=data if isinstance(data,list) else [data]
        while stack:
            node=stack.pop()
            if not isinstance(node,dict):continue
            if node.get("@type")=="JobPosting":out.append(node)
            if isinstance(node.get("@graph"),list):stack.extend(node["@graph"])
    return out

def _location(j: dict) -> str|None:
    loc=j.get("jobLocation");rows=loc if isinstance(loc,list) else [loc] if loc else []
    vals=[]
    for row in rows:
        if not isinstance(row,dict):continue
        a=row.get("address") or {}
        if isinstance(a,dict):
            x=", ".join(str(a.get(k)) for k in ("addressLocality","addressRegion","addressCountry") if a.get(k))
            if x:vals.append(x)
    return "; ".join(vals) or None

def _is_de(t,d):
    h=(t+" "+d[:3000]).lower()
    return any(x in h for x in ("data engineer","data engineering","data platform engineer","data infrastructure engineer","data integration engineer","etl engineer","analytics engineer","big data engineer"))

def fetch_jobs(company: str, search_url: str, timeout: int=25) -> list[dict]:
    """Collect public Paylocity Recruiting postings and detail pages."""
    body=_get(search_url,timeout);candidates=[(search_url,j) for j in _postings(body)]
    links=[];seen_links=set()
    for href in re.findall(r'href=["\']([^"\']+)["\']',body,re.I):
        url=urljoin(search_url,html.unescape(href));low=url.lower()
        if not any(x in low for x in ("/details/","/job/","/jobs/","jobid=")) or url in seen_links:continue
        seen_links.add(url);links.append(url)
    for url in links[:300]:
        try:detail=_get(url,timeout)
        except Exception:continue
        candidates.extend((url,j) for j in _postings(detail))
    tenant=urlparse(search_url).netloc+urlparse(search_url).path.split("/")[1] if len(urlparse(search_url).path.split("/"))>1 else urlparse(search_url).netloc
    out=[];seen=set()
    for page,j in candidates:
        title=_plain(j.get("title"));desc=_plain(j.get("description"))
        if not _is_de(title,desc):continue
        url=str(j.get("url") or page);ident=j.get("identifier") or url
        if isinstance(ident,dict):ident=ident.get("value") or ident.get("name") or url
        ident=str(ident)
        if ident in seen:continue
        seen.add(ident)
        out.append({"external_id":f"paylocity:{tenant}:{ident}","source":"paylocity","company_key":company,
          "title":title,"location":_location(j),"url":url,"original_url":url,"ats_provider":"paylocity",
          "ats_identifier":tenant,"job_id":ident,"description":desc,"description_complete":bool(desc),
          "updated_at":j.get("datePosted") or j.get("validThrough")})
    return out
