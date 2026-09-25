from __future__ import annotations

import html, json, re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

UA={"User-Agent":"Mozilla/5.0","Accept":"text/html,application/json,*/*"}

def _get(url: str, timeout: int=25) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _plain(value) -> str:
    value=html.unescape(str(value or ""))
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",value)).strip()

def _jobposting(body: str) -> list[dict]:
    out=[]
    for raw in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',body,re.I|re.S):
        try:data=json.loads(html.unescape(raw.strip()))
        except Exception:continue
        stack=data if isinstance(data,list) else [data]
        while stack:
            node=stack.pop()
            if not isinstance(node,dict):continue
            if node.get("@type")=="JobPosting":out.append(node)
            graph=node.get("@graph")
            if isinstance(graph,list):stack.extend(graph)
    return out

def _location(j: dict) -> str|None:
    loc=j.get("jobLocation")
    rows=loc if isinstance(loc,list) else [loc] if loc else []
    vals=[]
    for row in rows:
        if not isinstance(row,dict):continue
        addr=row.get("address") or {}
        if isinstance(addr,dict):
            text=", ".join(str(addr.get(k)) for k in ("addressLocality","addressRegion","addressCountry") if addr.get(k))
            if text:vals.append(text)
    return "; ".join(vals) or None

def fetch_jobs(company: str, search_url: str, timeout: int=25) -> list[dict]:
    """Collect public UKG/UltiPro postings exposed by the tenant's rendered board.

    UKG tenants vary substantially. This adapter intentionally uses public
    structured JobPosting data and board links, with the generic crawler still
    available as fallback for unsupported tenant variants.
    """
    body=_get(search_url,timeout)
    jobs=_jobposting(body)
    out=[];seen=set()
    for j in jobs:
        title=_plain(j.get("title"))
        desc=_plain(j.get("description"))
        hay=(title+" "+desc[:2500]).lower()
        if not any(x in hay for x in ("data engineer","data engineering","data platform engineer","data infrastructure engineer","etl engineer","analytics engineer")):continue
        url=str(j.get("url") or search_url)
        ident=j.get("identifier") or url
        if isinstance(ident,dict):ident=ident.get("value") or ident.get("name") or url
        ident=str(ident)
        if ident in seen:continue
        seen.add(ident)
        out.append({"external_id":f"ukg:{company}:{ident}","source":"ukg","company_key":company,
          "title":title,"location":_location(j),"url":url,"original_url":url,
          "ats_provider":"ukg","ats_identifier":search_url,"job_id":ident,
          "description":desc,"description_complete":bool(desc),
          "updated_at":j.get("datePosted") or j.get("validThrough")})
    if out:return out

    # Some legacy UltiPro boards render ordinary opportunity links server-side.
    hrefs=re.findall(r'href=["\']([^"\']+)["\']',body,re.I)
    links=[];seen_links=set()
    for href in hrefs:
        url=urljoin(search_url,html.unescape(href))
        low=url.lower()
        if ("opportunitydetail" in low or "/job/" in low or "/jobs/" in low) and url not in seen_links:
            seen_links.add(url);links.append(url)
    for url in links[:200]:
        try:detail=_get(url,timeout)
        except Exception:continue
        rows=_jobposting(detail)
        for j in rows:
            title=_plain(j.get("title"));desc=_plain(j.get("description"))
            hay=(title+" "+desc[:2500]).lower()
            if not any(x in hay for x in ("data engineer","data engineering","data platform engineer","data infrastructure engineer","etl engineer","analytics engineer")):continue
            ident=j.get("identifier") or url
            if isinstance(ident,dict):ident=ident.get("value") or url
            ident=str(ident)
            if ident in seen:continue
            seen.add(ident)
            out.append({"external_id":f"ukg:{company}:{ident}","source":"ukg","company_key":company,
              "title":title,"location":_location(j),"url":url,"original_url":url,
              "ats_provider":"ukg","ats_identifier":search_url,"job_id":ident,
              "description":desc,"description_complete":bool(desc),
              "updated_at":j.get("datePosted") or j.get("validThrough")})
    return out
