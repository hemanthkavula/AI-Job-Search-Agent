from __future__ import annotations
import html, json, re
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen

UA={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/plain,*/*"}

def _get(url: str, timeout: int = 20) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _plain(value: str) -> str:
    value=html.unescape(value or "")
    value=re.sub(r"<script[\s\S]*?</script>"," ",value,flags=re.I)
    value=re.sub(r"<style[\s\S]*?</style>"," ",value,flags=re.I)
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",value)).strip()

def _page_config(base_url: str, timeout: int) -> tuple[str,str]:
    body=_get(base_url.rstrip("/")+"/requisitions",timeout)
    site=re.search(r"""data-sitenumber=["']([^"']+)""",body,re.I)
    api=re.search(r"""data-apibaseurl=["']([^"']+)""",body,re.I)
    if not site: site=re.search(r"""["']siteNumber["']\s*:\s*["']?([^"',}\s]+)""",body,re.I)
    if not api: api=re.search(r"""["']apiBaseUrl["']\s*:\s*["']([^"']+)""",body,re.I)
    if not api: api=re.search(r"""(https://[^"']+\.fa\.[^"']+?)(?:/hcmRestApi|/hcmUI)""",body,re.I)
    if not site: raise RuntimeError("Oracle Candidate Experience siteNumber not found")
    origin=f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    api_base=html.unescape(api.group(1)).rstrip("/") if api else origin
    api_base=re.sub(r"/hcmRestApi(?:/CandidateExperience)?/?$","",api_base,flags=re.I)
    return site.group(1), api_base

def _search(api_base: str, site: str, keyword: str, page: int, limit: int, timeout: int) -> dict:
    finder_values={"siteNumber":site,"limit":str(limit),"offset":str(page*limit)}
    if keyword:
        finder_values["keyword"]=f'"{keyword}"'
    finder="findReqs;"+",".join(f"{key}={value}" for key,value in finder_values.items())
    params={"onlyData":"true","expand":"requisitionList.secondaryLocations","finder":finder}
    url=api_base.rstrip("/")+"/hcmRestApi/resources/latest/recruitingCEJobRequisitions?"+urlencode(params)
    try:return json.loads(_get(url,timeout))
    except Exception as exc:raise RuntimeError(f"Oracle search failed url={url}: {type(exc).__name__}:{exc}") from exc

def _job_url(base_url: str, row: dict) -> str:
    ident=str(row.get("id") or row.get("requisitionId") or row.get("requisitionNumber") or "")
    return f"{base_url.rstrip('/')}/job/{ident}" if ident else f"{base_url.rstrip('/')}/requisitions"

def fetch_jobs(company: str, base_url: str, timeout: int = 20, max_pages: int | None = None) -> list[dict]:
    """Traverse the Oracle Candidate Experience board to exhaustion.

    No Data Engineering keyword/title filter is applied here. Discovery returns
    the board's public requisitions and the shared downstream classifier decides
    job family, U.S. eligibility, experience, sponsorship and freshness.
    """
    site,api_base=_page_config(base_url,timeout)
    out=[];seen=set();limit=25;page=0;pages_total=0;truncated=False
    while True:
        if max_pages is not None and page>=max_pages:
            truncated=True;break
        data=_search(api_base,site,"",page,limit,timeout);pages_total+=1
        items=data.get("items") or []
        result=items[0] if items and isinstance(items[0],dict) else {}
        rows=result.get("requisitionList") or []
        for row in rows:
            if not isinstance(row,dict):continue
            title=str(row.get("title") or row.get("requisitionTitle") or "")
            ident=str(row.get("id") or row.get("requisitionId") or row.get("requisitionNumber") or "")
            key=ident or title+"|"+str(row.get("primaryLocation") or "")
            if key in seen:continue
            seen.add(key);url=_job_url(base_url,row)
            desc=_plain(str(row.get("shortDescriptionStr") or row.get("shortDescription") or ""))
            primary=row.get("primaryLocation") or row.get("primaryWorkLocation") or "";secondary=row.get("secondaryLocations") or []
            if isinstance(primary,list):primary=", ".join(map(str,primary))
            location=str(primary or "")
            if not location and secondary:location=", ".join(str(x) for x in secondary[:3])
            out.append({"external_id":f"oracle:{company}:{key}","source":"oracle","company_key":company,"title":title,"location":location or None,"url":url,"original_url":url,"ats_provider":"oracle","ats_identifier":base_url,"job_id":ident or key,"description":desc,"description_complete":False,"updated_at":row.get("postedDate") or row.get("postingEndDate")})
        total=int(result.get("totalJobsCount") or 0);offset=int(result.get("offset") or page*limit);used_limit=int(result.get("limit") or limit)
        if not rows or (total and offset+used_limit>=total) or len(rows)<used_limit:break
        page+=1
    state="TRUNCATED" if truncated else "EXHAUSTED"
    print(f"Oracle / {company}: {len(out)} jobs, {pages_total} pages, pagination={state}",flush=True)
    return out
