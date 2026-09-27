from __future__ import annotations
import html, json, re
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen

UA={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/plain,*/*"}

TITLE_RE=re.compile(r"\b(data (?:engineer|engineering|platform|infrastructure|pipeline)|big data engineer|etl engineer|analytics engineer|database engineer)\b",re.I)

def _get(url: str, timeout: int = 20) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _plain(value: str) -> str:
    value=html.unescape(value or "")
    value=re.sub(r"<script[\\s\\S]*?</script>"," ",value,flags=re.I)
    value=re.sub(r"<style[\\s\\S]*?</style>"," ",value,flags=re.I)
    return re.sub(r"\\s+"," ",re.sub(r"<[^>]+>"," ",value)).strip()

def _page_config(base_url: str, timeout: int) -> tuple[str,str]:
    body=_get(base_url.rstrip("/")+"/requisitions",timeout)
    site=re.search(r"""data-sitenumber=["']([^"']+)""",body,re.I)
    api=re.search(r"""data-apibaseurl=["']([^"']+)""",body,re.I)
    if not site:
        raise RuntimeError("Oracle Candidate Experience siteNumber not found")
    origin=f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    api_base=html.unescape(api.group(1)).rstrip("/") if api else origin
    # CX_CONFIG apiBaseUrl is the FA host; tolerate pages that expose an hcmRestApi suffix.
    api_base=re.sub(r"/hcmRestApi(?:/CandidateExperience)?/?$","",api_base,flags=re.I)
    return site.group(1), api_base

def _search(api_base: str, site: str, keyword: str, page: int, limit: int, timeout: int) -> dict:
    find_params={"siteNumber":site,"limit":limit,"offset":page*limit,"keyword":f'"{keyword}"'}
    # Oracle's current CE client uses recruitingCEJobRequisitions + findReqs.
    path="/hcmRestApi/recruitingCEJobRequisitions"
    params={
        "onlyData":"true",
        "expand":"requisitionList.secondaryLocations",
        "finder":"findReqs;:findParams:",
        "findParams":json.dumps(find_params,separators=(",",":")),
    }
    url=api_base.rstrip("/")+path+"?"+urlencode(params)
    try:
        return json.loads(_get(url,timeout))
    except Exception as exc:
        raise RuntimeError(f"Oracle search failed url={url}: {type(exc).__name__}:{exc}") from exc

def _job_url(base_url: str, row: dict) -> str:
    ident=str(row.get("id") or row.get("requisitionId") or row.get("requisitionNumber") or "")
    lang=str(row.get("contentLocale") or "en")
    return f"{base_url.rstrip('/')}/job/{ident}" if ident else f"{base_url.rstrip('/')}/requisitions"

def fetch_jobs(company: str, base_url: str, timeout: int = 20) -> list[dict]:
    site,api_base=_page_config(base_url,timeout)
    out=[];seen=set();limit=25
    # Search several DE-family terms because Oracle keyword search is phrase-sensitive.
    for keyword in ("data engineer","data engineering","data platform","data infrastructure","data pipeline","etl engineer","analytics engineer","database engineer"):
        for page in range(0,20):
            data=_search(api_base,site,keyword,page,limit,timeout)
            items=data.get("items") or []
            result=items[0] if items and isinstance(items[0],dict) else {}
            rows=result.get("requisitionList") or []
            for row in rows:
                if not isinstance(row,dict): continue
                title=str(row.get("title") or row.get("requisitionTitle") or "")
                if not TITLE_RE.search(title): continue
                ident=str(row.get("id") or row.get("requisitionId") or row.get("requisitionNumber") or "")
                key=ident or title+"|"+str(row.get("primaryLocation") or "")
                if key in seen: continue
                seen.add(key)
                url=_job_url(base_url,row)
                desc=_plain(str(row.get("shortDescriptionStr") or row.get("shortDescription") or ""))
                primary=row.get("primaryLocation") or row.get("primaryWorkLocation") or ""
                secondary=row.get("secondaryLocations") or []
                if isinstance(primary,list): primary=", ".join(map(str,primary))
                location=str(primary or "")
                if not location and secondary: location=", ".join(str(x) for x in secondary[:3])
                out.append({
                    "external_id":f"oracle:{company}:{key}","source":"oracle","company_key":company,
                    "title":title,"location":location or None,"url":url,"original_url":url,
                    "ats_provider":"oracle","ats_identifier":base_url,"job_id":ident or key,
                    "description":desc,"description_complete":False,
                    "updated_at":row.get("postedDate") or row.get("postingEndDate"),
                })
            total=int(result.get("totalJobsCount") or 0)
            offset=int(result.get("offset") or page*limit)
            used_limit=int(result.get("limit") or limit)
            if not rows or offset+used_limit>=total: break
    print(f"Oracle / {company}: {len(out)} DE jobs",flush=True)
    return out
