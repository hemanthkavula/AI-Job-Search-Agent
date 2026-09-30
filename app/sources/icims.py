from __future__ import annotations
import html, json, re
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

UA={"User-Agent":"AI-Job-Search-Agent/0.8","Accept":"text/html,application/xhtml+xml"}

def _get(url: str, timeout: int) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:return resp.read().decode("utf-8","replace")

def _job_links(base_url: str, text: str) -> list[str]:
    links=re.findall(r"href=[\"']([^\"']*/jobs/\d+[^\"']*)",text,re.I);out=[];seen=set()
    for href in links:
        url=urljoin(base_url,html.unescape(href))
        if url not in seen:seen.add(url);out.append(url)
    return out

def _jsonld_job(text: str) -> dict:
    pattern=r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>"
    for raw in re.findall(pattern,text,re.I|re.S):
        try:data=json.loads(html.unescape(raw.strip()))
        except Exception:continue
        stack=data if isinstance(data,list) else [data]
        while stack:
            row=stack.pop()
            if not isinstance(row,dict):continue
            if row.get("@type")=="JobPosting":return row
            if isinstance(row.get("@graph"),list):stack.extend(row["@graph"])
    return {}

def fetch_jobs(company: str, base_url: str, timeout: int = 20, max_pages: int|None = None) -> list[dict]:
    """Traverse the public iCIMS board without a job-family search constraint.

    Pagination continues to the provider/link frontier. Job-family, experience,
    U.S. location, sponsorship and other eligibility decisions are downstream.
    """
    base=base_url.rstrip("/")+"/";links=[];seen=set();page=1;truncated=False;pages=0
    while True:
        if max_pages is not None and page>max_pages:truncated=True;break
        # ss=1/pr are retained because they are iCIMS board controls, but no
        # searchKeyword is supplied: collect the complete visible board.
        query=urlencode({"ss":"1","pr":page});text=_get(urljoin(base,"jobs/search?")+query,timeout);pages+=1
        page_links=_job_links(base,text)
        if not page_links:break
        added=0
        for link in page_links:
            if link not in seen:seen.add(link);links.append(link);added+=1
        if not added:break
        page+=1
    out=[]
    for url in links:
        try:text=_get(url,timeout)
        except Exception:continue
        j=_jsonld_job(text)
        if not j:continue
        ident=str(j.get("identifier") or "")
        if isinstance(j.get("identifier"),dict):ident=str(j["identifier"].get("value") or "")
        if not ident:
            m=re.search(r"/jobs/(\d+)",url);ident=m.group(1) if m else url
        loc=j.get("jobLocation") or {}
        if isinstance(loc,list):loc=loc[0] if loc else {}
        addr=loc.get("address") or {} if isinstance(loc,dict) else {};location=", ".join(str(addr.get(k) or "") for k in ("addressLocality","addressRegion","addressCountry") if addr.get(k));desc=re.sub(r"<[^>]+>"," ",html.unescape(j.get("description") or ""))
        out.append({"external_id":f"icims:{company}:{ident}","source":"icims","company_key":company,"title":j.get("title") or "","location":location or None,"url":url,"original_url":url,"ats_provider":"icims","ats_identifier":base_url,"job_id":ident,"description":re.sub(r"\s+"," ",desc).strip(),"description_complete":bool(desc.strip()),"posted_on":j.get("datePosted"),"updated_at":j.get("datePosted"),"valid_through":j.get("validThrough")})
    print(f"iCIMS / {company}: {len(links)} job links, {len(out)} detailed jobs, {pages} search pages, pagination={'TRUNCATED' if truncated else 'EXHAUSTED_OR_FRONTIER'}",flush=True)
    return out
