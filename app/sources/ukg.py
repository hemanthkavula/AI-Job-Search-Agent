from __future__ import annotations

import html, json, re
from urllib.parse import urljoin
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
    loc=j.get("jobLocation"); rows=loc if isinstance(loc,list) else [loc] if loc else []
    vals=[]
    for row in rows:
        if not isinstance(row,dict):continue
        addr=row.get("address") or {}
        if isinstance(addr,dict):
            text=", ".join(str(addr.get(k)) for k in ("addressLocality","addressRegion","addressCountry") if addr.get(k))
            if text:vals.append(text)
    return "; ".join(vals) or None

def _embedded_opportunities(body: str) -> list[dict]:
    out=[];seen=set();decoder=json.JSONDecoder()
    for m in re.finditer(r'\{"Id":"[0-9a-fA-F-]{36}","Featured":',body):
        try:row,_=decoder.raw_decode(body[m.start():])
        except Exception:continue
        if not isinstance(row,dict) or not row.get("Title") or not row.get("Id"):continue
        ident=str(row["Id"])
        if ident in seen:continue
        seen.add(ident);out.append(row)
    return out

def _embedded_location(row: dict) -> str|None:
    vals=[]
    for loc in row.get("Locations") or []:
        if not isinstance(loc,dict):continue
        addr=loc.get("Address") or {};state=addr.get("State") or {} if isinstance(addr,dict) else {};country=addr.get("Country") or {} if isinstance(addr,dict) else {}
        parts=[]
        if isinstance(addr,dict) and addr.get("City"):parts.append(str(addr["City"]))
        if isinstance(state,dict) and state.get("Code"):parts.append(str(state["Code"]))
        if isinstance(country,dict) and country.get("Code"):parts.append(str(country["Code"]))
        label=", ".join(parts) or _plain(loc.get("LocalizedName") or loc.get("LocalizedDescription"))
        if label and label not in vals:vals.append(label)
    return "; ".join(vals) or None

def fetch_jobs(company: str, search_url: str, timeout: int=25) -> list[dict]:
    """Collect all public UKG/UltiPro postings visible from the tenant board.

    Discovery is intentionally high-recall. The shared downstream classifier is
    responsible for deciding job family and eligibility.
    """
    body=_get(search_url,timeout);out=[];seen=set()

    for row in _embedded_opportunities(body):
        title=_plain(row.get("Title"));desc=_plain(row.get("BriefDescription"));ident=str(row.get("Id"))
        url=search_url.rstrip("/")+"/OpportunityDetail?opportunityId="+ident
        if ident in seen:continue
        seen.add(ident)
        out.append({"external_id":f"ukg:{company}:{ident}","source":"ukg","company_key":company,
          "title":title,"location":_embedded_location(row),"url":url,"original_url":url,
          "ats_provider":"ukg","ats_identifier":search_url,"job_id":ident,
          "description":desc,"description_complete":False,"updated_at":row.get("PostedDate")})

    for j in _jobposting(body):
        title=_plain(j.get("title"));desc=_plain(j.get("description"));url=str(j.get("url") or search_url)
        ident=j.get("identifier") or url
        if isinstance(ident,dict):ident=ident.get("value") or ident.get("name") or url
        ident=str(ident)
        if ident in seen:continue
        seen.add(ident)
        out.append({"external_id":f"ukg:{company}:{ident}","source":"ukg","company_key":company,
          "title":title,"location":_location(j),"url":url,"original_url":url,
          "ats_provider":"ukg","ats_identifier":search_url,"job_id":ident,
          "description":desc,"description_complete":bool(desc),
          "posted_on":j.get("datePosted"),"updated_at":j.get("datePosted"),"valid_through":j.get("validThrough")})

    # Always inspect ordinary detail links too. Different UKG variants can mix
    # embedded summaries with richer detail pages, so returning early loses jobs.
    hrefs=re.findall(r'href=["\']([^"\']+)["\']',body,re.I)
    links=[];seen_links=set()
    for href in hrefs:
        url=urljoin(search_url,html.unescape(href));low=url.lower()
        if ("opportunitydetail" in low or "/job/" in low or "/jobs/" in low) and url not in seen_links:
            seen_links.add(url);links.append(url)
    for url in links:
        try:detail=_get(url,timeout)
        except Exception:continue
        for j in _jobposting(detail):
            title=_plain(j.get("title"));desc=_plain(j.get("description"));ident=j.get("identifier") or url
            if isinstance(ident,dict):ident=ident.get("value") or ident.get("name") or url
            ident=str(ident)
            if ident in seen:continue
            seen.add(ident);job_url=str(j.get("url") or url)
            out.append({"external_id":f"ukg:{company}:{ident}","source":"ukg","company_key":company,
              "title":title,"location":_location(j),"url":job_url,"original_url":job_url,
              "ats_provider":"ukg","ats_identifier":search_url,"job_id":ident,
              "description":desc,"description_complete":bool(desc),
              "posted_on":j.get("datePosted"),"updated_at":j.get("datePosted"),"valid_through":j.get("validThrough")})
    print(f"UKG / {company}: {len(out)} jobs discovered",flush=True)
    return out
