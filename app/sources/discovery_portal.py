from __future__ import annotations
import hashlib, html, json, re
from urllib.parse import urljoin
from urllib.request import Request, urlopen

UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.9"}
DE_TERMS=("data engineer","data engineering","data platform engineer","data infrastructure engineer","data pipeline engineer","data integration engineer","analytics engineer","big data engineer","etl engineer")

def _get(url:str,timeout:int=20)->str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as r:
        return r.read().decode("utf-8","replace")

def _plain(v)->str:
    v=html.unescape(str(v or ""))
    v=re.sub(r"<script[\s\S]*?</script>"," ",v,flags=re.I)
    v=re.sub(r"<style[\s\S]*?</style>"," ",v,flags=re.I)
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",v)).strip()

def _jobpostings(body:str)->list[dict]:
    out=[]
    pat=r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for raw in re.findall(pat,body,re.I|re.S):
        try:data=json.loads(html.unescape(raw.strip()))
        except Exception:continue
        rows=data if isinstance(data,list) else [data]
        for row in rows:
            if not isinstance(row,dict):continue
            nodes=[row]+(row.get("@graph") if isinstance(row.get("@graph"),list) else [])
            out.extend(x for x in nodes if isinstance(x,dict) and x.get("@type")=="JobPosting")
    return out

def _location(j:dict)->str|None:
    vals=[];locs=j.get("jobLocation") or []
    if isinstance(locs,dict):locs=[locs]
    for loc in locs if isinstance(locs,list) else []:
        if not isinstance(loc,dict):continue
        a=loc.get("address") or {}
        if isinstance(a,dict):
            vals.append(", ".join(str(a.get(k)) for k in ("addressLocality","addressRegion","addressCountry") if a.get(k)))
    if str(j.get("jobLocationType") or "").upper()=="TELECOMMUTE":vals.append("Remote")
    return " | ".join(x for x in vals if x) or None

def _normalize(provider:str,j:dict,page_url:str)->dict|None:
    title=_plain(j.get("title"));desc=_plain(j.get("description"))
    if not any(t in (title+" "+desc[:2500]).lower() for t in DE_TERMS):return None
    org=j.get("hiringOrganization")
    company=_plain(org.get("name")) if isinstance(org,dict) else _plain(org)
    url=urljoin(page_url,str(j.get("url") or page_url))
    ident=j.get("identifier")
    if isinstance(ident,dict):ident=ident.get("value") or ident.get("name")
    stable=str(ident or url or company+":"+title)
    sid=hashlib.sha1(stable.encode()).hexdigest()[:20]
    return {"external_id":f"{provider}:{sid}","source":provider,"company_key":company or "Unknown","title":title,
      "location":_location(j),"employment_type":j.get("employmentType"),"url":url,"original_url":url,
      "description":desc,"description_complete":bool(desc),"updated_at":j.get("datePosted"),"posted_on":j.get("datePosted"),
      "valid_through":j.get("validThrough"),"discovery_only":True,"authoritative_source":False,"portal_source":provider}

def fetch_jobs(provider:str,search_url:str,job_url_pattern:str,timeout:int=20)->list[dict]:
    """Crawl a public job portal strictly as a discovery feeder.

    Every returned row is marked discovery_only and must resolve to an
    authoritative employer/ATS posting before resume generation.
    """
    body=_get(search_url,timeout);out=[];seen=set()
    for j in _jobpostings(body):
        row=_normalize(provider,j,search_url)
        if row and row["external_id"] not in seen:
            seen.add(row["external_id"]);out.append(row)
    rx=re.compile(job_url_pattern.replace("\\","\"),re.I)
    links=[]
    for href in re.findall(r'href=["\']([^"\']+)["\']',body,re.I):
        u=urljoin(search_url,html.unescape(href))
        if rx.search(u) and u not in links:links.append(u)
    for u in links[:250]:
        try:detail=_get(u,timeout)
        except Exception:continue
        for j in _jobpostings(detail):
            row=_normalize(provider,j,u)
            if row and row["external_id"] not in seen:
                seen.add(row["external_id"]);out.append(row)
    print(f"DiscoveryPortal / {provider}: {len(out)} DE jobs",flush=True)
    return out
