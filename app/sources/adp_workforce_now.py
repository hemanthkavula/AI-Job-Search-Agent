from __future__ import annotations

import html, json, re
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

UA={"User-Agent":"Mozilla/5.0","Accept":"text/html,application/json,*/*"}

def _get(url: str, timeout: int=25) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _plain(value) -> str:
    value=html.unescape(str(value or ""))
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",value)).strip()

def _jobpostings(body: str) -> list[dict]:
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
    loc=j.get("jobLocation"); rows=loc if isinstance(loc,list) else [loc] if loc else []
    vals=[]
    for row in rows:
        if not isinstance(row,dict):continue
        addr=row.get("address") or {}
        if isinstance(addr,dict):
            text=", ".join(str(addr.get(k)) for k in ("addressLocality","addressRegion","addressCountry") if addr.get(k))
            if text:vals.append(text)
    return "; ".join(vals) or None

def fetch_jobs(company: str, search_url: str, timeout: int=25) -> list[dict]:
    """Collect every public ADP Workforce Now posting exposed by the board.

    Source adapters maximize recall. Job-family, experience, work-authorization,
    location and other eligibility decisions belong to the shared downstream
    classifier, so this adapter must not discard jobs before that stage.
    """
    body=_get(search_url,timeout);out=[];seen=set()
    candidates=[(search_url,j) for j in _jobpostings(body)]

    hrefs=re.findall(r'href=["\']([^"\']+)["\']',body,re.I)
    links=[];seen_links=set()
    for href in hrefs:
        url=urljoin(search_url,html.unescape(href))
        low=url.lower()
        if any(x in low for x in ("jobdetail","job-details","jobdetails","recruitment.html")) and url not in seen_links:
            seen_links.add(url);links.append(url)
    # Do not impose an arbitrary per-board detail-link ceiling. Large employers
    # can legitimately expose hundreds or thousands of openings.
    for url in links:
        try:detail=_get(url,timeout)
        except Exception:continue
        for j in _jobpostings(detail):candidates.append((url,j))

    parsed=urlparse(search_url);q=parse_qs(parsed.query)
    tenant=(q.get("cid") or q.get("ccId") or [parsed.netloc])[0]
    for page_url,j in candidates:
        title=_plain(j.get("title"));desc=_plain(j.get("description"))
        url=str(j.get("url") or page_url)
        ident=j.get("identifier") or url
        if isinstance(ident,dict):ident=ident.get("value") or ident.get("name") or url
        ident=str(ident)
        if ident in seen:continue
        seen.add(ident)
        out.append({"external_id":f"adp:{tenant}:{ident}","source":"adp_workforce_now","company_key":company,
          "title":title,"location":_location(j),"url":url,"original_url":url,
          "ats_provider":"adp_workforce_now","ats_identifier":tenant,"job_id":ident,
          "description":desc,"description_complete":bool(desc),
          "posted_on":j.get("datePosted"),"updated_at":j.get("datePosted"),"valid_through":j.get("validThrough")})
    print(f"ADP / {company}: {len(out)} jobs discovered",flush=True)
    return out
