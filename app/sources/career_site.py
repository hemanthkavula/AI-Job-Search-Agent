from __future__ import annotations
import html, json, re
from http.client import IncompleteRead
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.9"}

def _get(url: str, timeout: int = 20) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _plain(value: str) -> str:
    value=html.unescape(value or "")
    value=re.sub(r"<script[\\s\\S]*?</script>"," ",value,flags=re.I)
    value=re.sub(r"<style[\\s\\S]*?</style>"," ",value,flags=re.I)
    return re.sub(r"\\s+"," ",re.sub(r"<[^>]+>"," ",value)).strip()

def _jobpostings(body: str) -> list[dict]:
    """Return all schema.org JobPosting objects embedded in a career page."""
    found=[]
    pat = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for raw in re.findall(pat, body, re.I | re.S):
        try:
            data=json.loads(html.unescape(raw.strip()))
        except Exception:
            continue
        rows=data if isinstance(data,list) else [data]
        for row in rows:
            if not isinstance(row,dict):
                continue
            nodes=[row]
            if isinstance(row.get("@graph"),list):
                nodes.extend(row["@graph"])
            for node in nodes:
                if isinstance(node,dict) and node.get("@type")=="JobPosting":
                    found.append(node)
    return found

def _identifier(j: dict, fallback: str) -> str:
    ident=j.get("identifier")
    if isinstance(ident,dict):
        ident=ident.get("value") or ident.get("name")
    return str(ident or j.get("url") or fallback)

def _direct_apply_url(j: dict, fallback: str) -> str:
    return str(j.get("url") or fallback)

def _dedupe_jobs(rows: list[dict]) -> list[dict]:
    """Prefer one authoritative record per stable job id/URL."""
    out=[]; seen=set()
    for row in rows:
        key=str(row.get("job_id") or row.get("external_id") or row.get("url") or "").strip().lower()
        if not key: key=f"{row.get('company_key','')}|{row.get('title','')}|{row.get('location','')}".lower()
        if key in seen: continue
        seen.add(key); out.append(row)
    return out

def _salary(j: dict) -> dict | None:
    base=j.get("baseSalary")
    if not isinstance(base,dict): return None
    value=base.get("value")
    currency=base.get("currency")
    unit=None; minimum=None; maximum=None
    if isinstance(value,dict):
        minimum=value.get("minValue")
        maximum=value.get("maxValue")
        unit=value.get("unitText")
        if minimum is None and maximum is None and value.get("value") is not None:
            minimum=maximum=value.get("value")
    elif value is not None:
        minimum=maximum=value
    if minimum is None and maximum is None: return None
    return {"currency":currency,"min":minimum,"max":maximum,"unit":unit}

def _remote_flag(j: dict) -> bool:
    if str(j.get("jobLocationType") or "").upper()=="TELECOMMUTE": return True
    text=" ".join(str(x) for x in (j.get("title"),j.get("description"),j.get("jobLocationType")) if x).lower()
    return bool(re.search(r"\b(remote|telecommute|work from home)\b",text))

def _dates(j: dict) -> tuple[str | None, str | None]:
    posted=j.get("datePosted")
    expires=j.get("validThrough")
    return (str(posted) if posted else None, str(expires) if expires else None)

def _job_type(j: dict) -> str | None:
    value=j.get("employmentType")
    if isinstance(value,list): value=", ".join(str(x) for x in value if x)
    return _plain(str(value)) or None if value else None

def _organization(j: dict) -> str | None:
    org=j.get("hiringOrganization")
    if isinstance(org,dict):
        return _plain(str(org.get("name") or "")) or None
    return _plain(str(org)) or None if org else None

def _location(j: dict) -> str | None:
    """Extract human-readable location evidence from schema.org JobPosting."""
    parts=[]
    locs=j.get("jobLocation") or []
    if isinstance(locs,dict): locs=[locs]
    for loc in locs if isinstance(locs,list) else []:
        if not isinstance(loc,dict): continue
        addr=loc.get("address") or {}
        if isinstance(addr,str):
            parts.append(_plain(addr))
            continue
        if isinstance(addr,dict):
            vals=[addr.get("addressLocality"),addr.get("addressRegion"),addr.get("postalCode"),addr.get("addressCountry")]
            parts.append(", ".join(str(v) for v in vals if v))
    req=j.get("applicantLocationRequirements") or []
    if isinstance(req,dict): req=[req]
    for item in req if isinstance(req,list) else []:
        if isinstance(item,dict):
            name=item.get("name")
            if name: parts.append(str(name))
        elif item: parts.append(str(item))
    if str(j.get("jobLocationType") or "").upper()=="TELECOMMUTE":
        parts.append("Remote")
    clean=[]
    for p in parts:
        p=_plain(str(p))
        if p and p not in clean: clean.append(p)
    return " | ".join(clean) or None

def _jsonld(body: str) -> dict:
    pat = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for raw in re.findall(pat, body, re.I | re.S):
        try:
            data = json.loads(html.unescape(raw.strip()))
        except Exception:
            continue
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            if isinstance(row, dict) and row.get("@type") == "JobPosting":
                return row
            if isinstance(row, dict) and isinstance(row.get("@graph"), list):
                for node in row["@graph"]:
                    if isinstance(node, dict) and node.get("@type") == "JobPosting":
                        return node
    return {}

def _workable_public(company: str, search_url: str, timeout: int) -> list[dict]:
    m=re.search(r"apply\\.workable\\.com/([^/?#]+)",search_url,re.I)
    if not m:return []
    slug=m.group(1)
    payload=json.loads(_get(f"https://www.workable.com/api/accounts/{slug}?details=true",timeout))
    out=[]
    for j in payload.get("jobs",[]):
        title=str(j.get("title") or "")
        desc=_plain(str(j.get("description") or j.get("full_description") or ""))
        hay=(title+" "+desc[:2500]).lower()
        if not any(term in hay for term in ("data engineer","data engineering","data platform engineer","big data engineer","etl engineer")):continue
        shortcode=str(j.get("shortcode") or j.get("code") or "")
        url=j.get("url") or (f"https://apply.workable.com/{slug}/j/{shortcode}" if shortcode else search_url)
        loc=", ".join(str(x) for x in (j.get("city"),j.get("state"),j.get("country")) if x)
        out.append({"external_id":f"workable:{slug}:{shortcode or url}","source":"workable","company_key":company,
          "title":title,"location":loc or None,"url":url,"original_url":url,"ats_provider":"workable",
          "ats_identifier":slug,"job_id":shortcode or url,"description":desc,"description_complete":bool(desc),
          "updated_at":j.get("published") or j.get("created_at")})
    return out

def _detail_fallback(company: str, search_url: str, timeout: int) -> list[dict]:
    low=search_url.lower()
    if not any(x in low for x in ("opportunitydetail","/jobdetail/","/jobs/details/","/apply/")): return []
    body=_get(search_url,timeout); j=_jsonld(body)
    title=_plain(str(j.get("title") or ""))
    if not title:
        m=re.search(r"<title>(.*?)</title>",body,re.I|re.S); title=_plain(m.group(1)) if m else ""
    text=_plain(str(j.get("description") or body)); hay=(title+" "+text[:3000]).lower()
    if not any(t in hay for t in ("data engineer","data engineering","data platform engineer","big data engineer","etl engineer","analytics engineer")): return []
    ident=_identifier(j,search_url)
    host=urlparse(search_url).netloc
    return [{"external_id":f"career_site:{company}:{ident}","source":"career_site","company_key":company,"title":title,"location":_location(j),"url":search_url,"original_url":search_url,"ats_provider":host,"ats_identifier":host,"job_id":str(ident),"description":text,"description_complete":bool(text),"updated_at":j.get("datePosted") or j.get("validThrough")}]

def fetch_jobs(company: str, search_url: str, job_url_pattern: str, timeout: int = 20) -> list[dict]:
    """Crawl a public employer career search page for Data Engineering jobs."""
    if "apply.workable.com/" in search_url.lower():
        try:return _workable_public(company,search_url,timeout)
        except Exception:pass
    body=_get(search_url,timeout)
    embedded=[]
    for j in _jobpostings(body):
        title=_plain(str(j.get("title") or ""))
        desc=_plain(str(j.get("description") or ""))
        hay=(title+" "+desc[:2500]).lower()
        if not any(t in hay for t in ("data engineer","data engineering","data platform engineer","big data engineer","etl engineer","analytics engineer")):
            continue
        ident=_identifier(j,title)
        url=_direct_apply_url(j,search_url)
        embedded.append({"external_id":f"career_site:{company}:{ident}","source":"career_site","company_key":company,
          "title":title,"location":_location(j),"url":url,"original_url":url,"ats_provider":"career_site",
          "ats_identifier":search_url,"job_id":str(ident),"description":desc,"description_complete":bool(desc),
          "updated_at":j.get("datePosted") or j.get("validThrough"),"date_posted":_dates(j)[0],"valid_through":_dates(j)[1],"employment_type":_job_type(j),"hiring_organization":_organization(j),"remote":_remote_flag(j),"salary":_salary(j)})
    hrefs=re.findall(r"href=['\\\"]([^'\\\"]+)['\\\"]",body,re.I)
    # Older source configs may contain regexes double-escaped for JSON.
    # Normalize one escaping layer so valid static job links remain discoverable.
    normalized_pattern=job_url_pattern.replace("\\\\", "\\")
    rx=re.compile(normalized_pattern,re.I)
    links=[];seen=set()
    for href in hrefs:
        url=urljoin(search_url,html.unescape(href))
        if rx.search(url) and url not in seen:
            seen.add(url);links.append(url)
    if not links and not embedded:
        fallback=_detail_fallback(company,search_url,timeout)
        if fallback:return fallback
    out=list(embedded)
    embedded_urls={x.get("url") for x in embedded}
    for url in links:
        if url in embedded_urls:continue
        try:detail=_get(url,timeout)
        except Exception:continue
        j=_jsonld(detail)
        title=_plain(str(j.get("title") or ""))
        if not title:
            m=re.search(r"<title>(.*?)</title>",detail,re.I|re.S);title=_plain(m.group(1)) if m else ""
        text=_plain(str(j.get("description") or detail))
        hay=(title+" "+text[:2000]).lower()
        if not any(term in hay for term in ("data engineer","data platform engineer","big data engineer","etl engineer")):continue
        ident=_identifier(j,url)
        out.append({"external_id":f"career_site:{company}:{ident}","source":"career_site","company_key":company,
          "title":title,"location":None,"url":url,"original_url":url,"ats_provider":"career_site",
          "ats_identifier":search_url,"job_id":ident,"description":text,"description_complete":bool(text),
          "updated_at":j.get("datePosted") or j.get("validThrough")})
    out=_dedupe_jobs(out)
    print(f"CareerSite / {company}: {len(out)} DE jobs",flush=True)
    return out


def validate_source(company: str, search_url: str, job_url_pattern: str, timeout: int = 12) -> dict:
    """Validate a configured career source without treating anti-bot blocks as 404s."""
    result={"company":company,"search_url":search_url,"status":"unknown","http_status":None,"error":None}
    try:
        with urlopen(Request(search_url,headers=UA),timeout=timeout) as resp:
            result["http_status"]=getattr(resp,"status",None)
            try:
                raw=resp.read(250000)
            except IncompleteRead as exc:
                # Some career sites terminate chunked responses early. The
                # partial HTML is still sufficient for a non-destructive
                # source-health/link check, so do not crash the whole report.
                raw=exc.partial
                result["partial_response"]=True
            body=raw.decode("utf-8","replace")
        result["status"]="ok" if result["http_status"] in (None,200) else "http_error"
        normalized_pattern=job_url_pattern.replace("\\\\", "\\")
        rx=re.compile(normalized_pattern,re.I)
        hrefs=re.findall(r"href=[\'\\\"]([^\'\\\"]+)[\'\\\"]",body,re.I)
        result["matching_job_links"]=sum(1 for h in hrefs if rx.search(urljoin(search_url,html.unescape(h))))
        result["embedded_jobpostings"]=len(_jobpostings(body))
        result["discoverable_jobs"]=result["matching_job_links"]+result["embedded_jobpostings"]
    except HTTPError as exc:
        result["http_status"]=exc.code
        result["status"]="broken" if exc.code in (404,410) else "blocked_or_http_error"
        result["error"]=str(exc)
    except (URLError,TimeoutError,OSError,IncompleteRead) as exc:
        result["status"]="unreachable"
        result["error"]=str(exc)
    except re.error as exc:
        result["status"]="invalid_pattern"
        result["error"]=str(exc)
    return result
