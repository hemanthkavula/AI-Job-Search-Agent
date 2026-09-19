from __future__ import annotations
import html, json, re
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

UA={"User-Agent":"AI-Job-Search-Agent/0.6","Accept":"text/html,application/xhtml+xml"}

def _get(url: str, timeout: int = 20) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _plain(value: str) -> str:
    value=html.unescape(value or "")
    value=re.sub(r"<script[\\s\\S]*?</script>"," ",value,flags=re.I)
    value=re.sub(r"<style[\\s\\S]*?</style>"," ",value,flags=re.I)
    return re.sub(r"\\s+"," ",re.sub(r"<[^>]+>"," ",value)).strip()

def _job_links(base_url: str, body: str) -> list[str]:
    links=re.findall(r'href=[\\"\\']([^\\"\\']*/job/[^\\"\\'?#]+)',body,re.I)
    out=[];seen=set()
    for href in links:
        url=urljoin(base_url,html.unescape(href))
        if url not in seen:
            seen.add(url);out.append(url)
    return out

def _jsonld(body: str) -> dict:
    for raw in re.findall(r"<script[^>]+type=[\\"\\']application/ld\\+json[\\"\\'][^>]*>(.*?)</script>",body,re.I|re.S):
        try:data=json.loads(html.unescape(raw.strip()))
        except Exception:continue
        for row in (data if isinstance(data,list) else [data]):
            if isinstance(row,dict) and row.get("@type")=="JobPosting":return row
    return {}

def fetch_jobs(company: str, base_url: str, timeout: int = 20) -> list[dict]:
    base=base_url.rstrip("/")+"/"
    query=urlencode({"keyword":"data engineer","location":"United States"})
    body=_get(urljoin(base,"requisitions?")+query,timeout)
    links=_job_links(base,body)
    out=[]
    for url in links:
        try:detail=_get(url,timeout)
        except Exception:continue
        j=_jsonld(detail); text=_plain(j.get("description") or detail)
        title=str(j.get("title") or "")
        if not title:
            m=re.search(r"<title>(.*?)</title>",detail,re.I|re.S);title=_plain(m.group(1)) if m else ""
        if "data engineer" not in (title+" "+text[:1000]).lower():continue
        ident=str(j.get("identifier") or "")
        if isinstance(j.get("identifier"),dict):ident=str(j["identifier"].get("value") or "")
        if not ident:
            m=re.search(r"/job/(\\d+)",url);ident=m.group(1) if m else url
        loc=j.get("jobLocation") or {}; loc=loc[0] if isinstance(loc,list) and loc else loc
        addr=loc.get("address") or {} if isinstance(loc,dict) else {}
        location=", ".join(str(addr.get(k) or "") for k in ("addressLocality","addressRegion","addressCountry") if addr.get(k))
        out.append({"external_id":f"oracle:{company}:{ident}","source":"oracle","company_key":company,
          "title":title,"location":location or None,"url":url,"original_url":url,
          "ats_provider":"oracle","ats_identifier":base_url,"job_id":ident,
          "description":text,"description_complete":bool(text),
          "updated_at":j.get("datePosted") or j.get("validThrough")})
    print(f"Oracle / {company}: {len(out)} DE jobs",flush=True)
    return out
