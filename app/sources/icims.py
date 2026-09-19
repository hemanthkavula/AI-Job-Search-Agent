from __future__ import annotations
import html, json, re
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

UA={"User-Agent":"AI-Job-Search-Agent/0.2","Accept":"text/html,application/xhtml+xml"}

def _get(url: str, timeout: int) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _job_links(base_url: str, text: str) -> list[str]:
    links=re.findall(r'href=["\\\']([^"\\\']*/jobs/\\d+[^"\\\']*)',text,re.I)
    out=[];seen=set()
    for href in links:
        url=urljoin(base_url,html.unescape(href))
        if url not in seen:
            seen.add(url);out.append(url)
    return out

def _jsonld_job(text: str) -> dict:
    for raw in re.findall(r'<script[^>]+type=["\\\']application/ld\\+json["\\\'][^>]*>(.*?)</script>',text,re.I|re.S):
        try:data=json.loads(html.unescape(raw.strip()))
        except Exception:continue
        rows=data if isinstance(data,list) else [data]
        for row in rows:
            if isinstance(row,dict) and row.get("@type")=="JobPosting":return row
    return {}

def fetch_jobs(company: str, base_url: str, timeout: int = 20, max_pages: int = 3) -> list[dict]:
    """Fetch public iCIMS postings by crawling search results and JobPosting JSON-LD."""
    base=base_url.rstrip("/")+"/"
    links=[];seen=set()
    for page in range(1,max_pages+1):
        query=urlencode({"ss":"1","searchKeyword":"data engineer","pr":page})
        text=_get(urljoin(base,"jobs/search?")+query,timeout)
        page_links=_job_links(base,text)
        if not page_links:break
        added=0
        for link in page_links:
            if link not in seen:seen.add(link);links.append(link);added+=1
        if not added:break
    out=[]
    for url in links:
        text=_get(url,timeout);j=_jsonld_job(text)
        if not j:continue
        ident=str(j.get("identifier") or "")
        if isinstance(j.get("identifier"),dict):ident=str(j["identifier"].get("value") or "")
        if not ident:
            m=re.search(r"/jobs/(\\d+)",url);ident=m.group(1) if m else url
        loc=j.get("jobLocation") or {}
        if isinstance(loc,list):loc=loc[0] if loc else {}
        addr=loc.get("address") or {} if isinstance(loc,dict) else {}
        location=", ".join(str(addr.get(k) or "") for k in ("addressLocality","addressRegion","addressCountry") if addr.get(k))
        desc=re.sub(r"<[^>]+>"," ",html.unescape(j.get("description") or ""))
        out.append({
            "external_id":f"icims:{company}:{ident}","source":"icims","company_key":company,
            "title":j.get("title") or "","location":location or None,"url":url,"original_url":url,
            "ats_provider":"icims","ats_identifier":base_url,"job_id":ident,
            "description":re.sub(r"\\s+"," ",desc).strip(),"description_complete":bool(desc.strip()),
            "updated_at":j.get("datePosted") or j.get("validThrough"),
        })
    return out
