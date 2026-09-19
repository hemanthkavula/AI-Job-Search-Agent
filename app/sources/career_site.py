from __future__ import annotations
import html, json, re
from urllib.parse import urljoin
from urllib.request import Request, urlopen

UA={"User-Agent":"AI-Job-Search-Agent/0.7","Accept":"text/html,application/xhtml+xml"}

def _get(url: str, timeout: int = 20) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _plain(value: str) -> str:
    value=html.unescape(value or "")
    value=re.sub(r"<script[\\s\\S]*?</script>"," ",value,flags=re.I)
    value=re.sub(r"<style[\\s\\S]*?</style>"," ",value,flags=re.I)
    return re.sub(r"\\s+"," ",re.sub(r"<[^>]+>"," ",value)).strip()

def _jsonld(body: str) -> dict:
    pat=r"<script[^>]+type=['\\\"]application/ld\\+json['\\\"][^>]*>(.*?)</script>"
    for raw in re.findall(pat,body,re.I|re.S):
        try:data=json.loads(html.unescape(raw.strip()))
        except Exception:continue
        for row in (data if isinstance(data,list) else [data]):
            if isinstance(row,dict) and row.get("@type")=="JobPosting":return row
    return {}

def fetch_jobs(company: str, search_url: str, job_url_pattern: str, timeout: int = 20) -> list[dict]:
    """Crawl a public employer career search page for Data Engineering jobs."""
    body=_get(search_url,timeout)
    hrefs=re.findall(r"href=['\\\"]([^'\\\"]+)['\\\"]",body,re.I)
    rx=re.compile(job_url_pattern,re.I)
    links=[];seen=set()
    for href in hrefs:
        url=urljoin(search_url,html.unescape(href))
        if rx.search(url) and url not in seen:
            seen.add(url);links.append(url)
    out=[]
    for url in links:
        try:detail=_get(url,timeout)
        except Exception:continue
        j=_jsonld(detail)
        title=_plain(str(j.get("title") or ""))
        if not title:
            m=re.search(r"<title>(.*?)</title>",detail,re.I|re.S);title=_plain(m.group(1)) if m else ""
        text=_plain(str(j.get("description") or detail))
        hay=(title+" "+text[:2000]).lower()
        if not any(term in hay for term in ("data engineer","data platform engineer","big data engineer","etl engineer")):continue
        ident=str(j.get("identifier") or "")
        if isinstance(j.get("identifier"),dict):ident=str(j["identifier"].get("value") or "")
        if not ident:ident=url
        out.append({"external_id":f"career_site:{company}:{ident}","source":"career_site","company_key":company,
          "title":title,"location":None,"url":url,"original_url":url,"ats_provider":"career_site",
          "ats_identifier":search_url,"job_id":ident,"description":text,"description_complete":bool(text),
          "updated_at":j.get("datePosted") or j.get("validThrough")})
    print(f"CareerSite / {company}: {len(out)} DE jobs",flush=True)
    return out
