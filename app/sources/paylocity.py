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


def _meta(body: str, prop: str) -> str:
    q=re.escape(prop)
    patterns=(
        rf'''(?is)<meta[^>]+(?:name|property)=["']{q}["'][^>]+content=["']([^"']+)["']''',
        rf'''(?is)<meta[^>]+content=["']([^"']+)["'][^>]+(?:name|property)=["']{q}["']''',
    )
    for pattern in patterns:
        m=re.search(pattern,body or "")
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def _visible_text(body: str) -> str:
    value=re.sub(r"(?is)<script[^>]*>.*?</script>"," ",body or "")
    value=re.sub(r"(?is)<style[^>]*>.*?</style>"," ",value)
    return _plain(value)


def fetch_job(company: str, url: str, timeout: int=25) -> dict | None:
    """Resolve one exact Paylocity posting through its server-rendered Details page."""
    m=re.search(r"/Recruiting/Jobs/(?:Apply|Details)/(\d+)",str(url or ""),re.I)
    if not m:
        return None
    job_id=m.group(1)
    parsed=urlparse(str(url))
    details=f"{parsed.scheme or 'https'}://{parsed.netloc}/Recruiting/Jobs/Details/{job_id}"
    try:
        body=_get(details,timeout)
    except Exception:
        return None

    postings=_postings(body)
    if postings:
        j=max(postings,key=lambda x:len(str(x.get("description") or "")))
        title=_plain(j.get("title"))
        desc=_plain(j.get("description"))
        canonical=str(j.get("url") or details)
        ident=j.get("identifier") or job_id
        if isinstance(ident,dict):
            ident=ident.get("value") or ident.get("name") or job_id
        org=j.get("hiringOrganization")
        resolved_company=_plain(org.get("name")) if isinstance(org,dict) else company
        return {
            "external_id":f"paylocity:{resolved_company or company}:{ident}",
            "source":"paylocity",
            "company_key":resolved_company or company,
            "company":resolved_company or company,
            "title":title,
            "location":_location(j),
            "url":canonical,
            "original_url":canonical,
            "ats_provider":"paylocity",
            "ats_identifier":job_id,
            "job_id":str(ident),
            "requisition_id":str(ident),
            "description":desc,
            "description_complete":bool(desc),
            "posted_at":j.get("datePosted"),
            "exact_job_metadata_source":"paylocity_details_jsonld",
        }

    og_title=_plain(_meta(body,"og:title"))
    og_desc=_plain(_meta(body,"og:description"))
    visible=_visible_text(body)
    resolved_company=company
    title=og_title
    if " - " in og_title:
        left,right=og_title.split(" - ",1)
        if left.strip() and right.strip():
            resolved_company=left.strip()
            title=right.strip()
    desc=max((og_desc,visible),key=len,default="")
    if not title or len(desc)<180:
        return None
    return {
        "external_id":f"paylocity:{resolved_company or company}:{job_id}",
        "source":"paylocity",
        "company_key":resolved_company or company,
        "company":resolved_company or company,
        "title":title,
        "location":None,
        "url":details,
        "original_url":details,
        "ats_provider":"paylocity",
        "ats_identifier":job_id,
        "job_id":job_id,
        "requisition_id":job_id,
        "description":desc,
        "description_complete":True,
        "exact_job_metadata_source":"paylocity_details_page",
    }
