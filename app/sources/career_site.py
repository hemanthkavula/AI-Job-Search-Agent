from __future__ import annotations
import html, json, re
from http.client import IncompleteRead
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.9"}

def _get(url: str, timeout: int = 20) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:return resp.read().decode("utf-8","replace")

def _plain(value: str) -> str:
    value=html.unescape(value or "");value=re.sub(r"<script[\s\S]*?</script>"," ",value,flags=re.I);value=re.sub(r"<style[\s\S]*?</style>"," ",value,flags=re.I)
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",value)).strip()

def _jobpostings(body: str) -> list[dict]:
    found=[];pat=r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for raw in re.findall(pat,body,re.I|re.S):
        try:data=json.loads(html.unescape(raw.strip()))
        except Exception:continue
        rows=data if isinstance(data,list) else [data]
        for row in rows:
            if not isinstance(row,dict):continue
            nodes=[row]+(row.get("@graph") if isinstance(row.get("@graph"),list) else [])
            found.extend(node for node in nodes if isinstance(node,dict) and node.get("@type")=="JobPosting")
    return found

def _identifier(j: dict, fallback: str) -> str:
    ident=j.get("identifier")
    if isinstance(ident,dict):ident=ident.get("value") or ident.get("name")
    return str(ident or j.get("url") or fallback)

def _canonical_url(url: str) -> str:
    try:
        p=urlparse(str(url))
        return p._replace(fragment="",query="").geturl() if p.scheme and p.netloc else str(url)
    except Exception:return str(url)

def _direct_apply_url(j: dict, fallback: str) -> str:return _canonical_url(str(j.get("url") or fallback))

def _dedupe_jobs(rows: list[dict]) -> list[dict]:
    out=[];seen=set()
    for row in rows:
        key=str(row.get("job_id") or row.get("external_id") or row.get("url") or "").strip().lower() or f"{row.get('company_key','')}|{row.get('title','')}|{row.get('location','')}".lower()
        if key in seen:continue
        seen.add(key);out.append(row)
    return out

def _work_hours(j):
    v=j.get("workHours");v=" | ".join(str(x) for x in v if x) if isinstance(v,list) else v;return _plain(str(v)) or None if v else None

def _occupational_category(j):
    v=j.get("occupationalCategory");v=" | ".join(str(x) for x in v if x) if isinstance(v,list) else v;return _plain(str(v)) or None if v else None

def _benefits(j):
    v=j.get("jobBenefits");v=" | ".join(str(x) for x in v if x) if isinstance(v,list) else v;return _plain(str(v)) or None if v else None

def _responsibilities(j):
    v=j.get("responsibilities");v=" | ".join(str(x) for x in v if x) if isinstance(v,list) else v;return _plain(str(v)) or None if v else None

def _language(j):
    v=j.get("inLanguage");v=(v.get("name") or v.get("@id")) if isinstance(v,dict) else v;v=", ".join(str(x) for x in v if x) if isinstance(v,list) else v;return _plain(str(v)) or None if v else None

def _industry(j):
    v=j.get("industry");v=", ".join(str(x) for x in v if x) if isinstance(v,list) else v;return _plain(str(v)) or None if v else None

def _source_quality(j):
    return {"has_structured_jobposting":True,"has_direct_job_url":bool(j.get("url")),"has_stable_identifier":bool(j.get("identifier")),"has_hiring_organization":bool(j.get("hiringOrganization")),"has_location_evidence":bool(j.get("jobLocation") or j.get("applicantLocationRequirements") or j.get("jobLocationType")),"has_employment_type":bool(j.get("employmentType")),"has_posting_date":bool(j.get("datePosted"))}

def _is_expired(j):
    value=j.get("validThrough")
    if not value:return False
    try:
        from datetime import datetime,timezone
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"));dt=dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        return dt<datetime.now(timezone.utc)
    except Exception:return False

def _freshness(j):
    if _is_expired(j):return "expired"
    if j.get("validThrough"):return "active_by_schema"
    if j.get("datePosted"):return "dated_no_expiry"
    return "unknown"

def _source_evidence(j,page_url):
    return {"authoritative_source":"employer_career_site","source_page_url":page_url,"schema_type":str(j.get("@type") or "JobPosting"),"direct_job_url":_canonical_url(str(j.get("url") or page_url)),"schema_expired":_is_expired(j),"freshness_evidence":_freshness(j),"source_quality_evidence":_source_quality(j)}

def _education_experience(j):return {"education_requirements":_plain(str(j.get("educationRequirements") or "")) or None,"experience_requirements":_plain(str(j.get("experienceRequirements") or "")) or None}

def _skills(j):
    v=j.get("skills") or j.get("qualifications");vals=[_plain(str(x)) for x in v] if isinstance(v,list) else [_plain(x) for x in re.split(r"[,;|]",v)] if isinstance(v,str) else []
    return [x for x in vals if x][:50]

def _salary(j):
    base=j.get("baseSalary")
    if not isinstance(base,dict):return None
    value=base.get("value");currency=base.get("currency");unit=None;minimum=None;maximum=None
    if isinstance(value,dict):
        minimum=value.get("minValue");maximum=value.get("maxValue");unit=value.get("unitText")
        if minimum is None and maximum is None and value.get("value") is not None:minimum=maximum=value.get("value")
    elif value is not None:minimum=maximum=value
    return None if minimum is None and maximum is None else {"currency":currency,"min":minimum,"max":maximum,"unit":unit}

def _remote_flag(j):
    if str(j.get("jobLocationType") or "").upper()=="TELECOMMUTE":return True
    text=" ".join(str(x) for x in (j.get("title"),j.get("description"),j.get("jobLocationType")) if x).lower();return bool(re.search(r"\b(remote|telecommute|work from home)\b",text))

def _dates(j):return (str(j.get("datePosted")) if j.get("datePosted") else None,str(j.get("validThrough")) if j.get("validThrough") else None)

def _job_type(j):
    v=j.get("employmentType");v=", ".join(str(x) for x in v if x) if isinstance(v,list) else v;return _plain(str(v)) or None if v else None

def _organization(j):
    org=j.get("hiringOrganization");return _plain(str(org.get("name") or "")) or None if isinstance(org,dict) else _plain(str(org)) or None if org else None

def _location(j):
    parts=[];locs=j.get("jobLocation") or [];locs=[locs] if isinstance(locs,dict) else locs
    for loc in locs if isinstance(locs,list) else []:
        if not isinstance(loc,dict):continue
        addr=loc.get("address") or {}
        if isinstance(addr,str):parts.append(_plain(addr));continue
        if isinstance(addr,dict):parts.append(", ".join(str(v) for v in (addr.get("addressLocality"),addr.get("addressRegion"),addr.get("postalCode"),addr.get("addressCountry")) if v))
    req=j.get("applicantLocationRequirements") or [];req=[req] if isinstance(req,dict) else req
    for item in req if isinstance(req,list) else []:
        if isinstance(item,dict) and item.get("name"):parts.append(str(item["name"]))
        elif item and not isinstance(item,dict):parts.append(str(item))
    if str(j.get("jobLocationType") or "").upper()=="TELECOMMUTE":parts.append("Remote")
    clean=[]
    for p in parts:
        p=_plain(str(p))
        if p and p not in clean:clean.append(p)
    return " | ".join(clean) or None

def _jsonld(body):
    rows=_jobpostings(body);return rows[0] if rows else {}

def _row(company,source,provider,identifier,page_url,j,description=None,title=None):
    title=_plain(str(title if title is not None else j.get("title") or ""));desc=_plain(str(description if description is not None else j.get("description") or ""));ident=_identifier(j,page_url);url=_direct_apply_url(j,page_url)
    return {"external_id":f"{source}:{company}:{ident}","source":source,"company_key":company,"title":title,"location":_location(j),"url":url,"original_url":url,"ats_provider":provider,"ats_identifier":identifier,"job_id":str(ident),"description":desc,"description_complete":bool(desc),"updated_at":j.get("datePosted"),"posted_on":j.get("datePosted"),"valid_through":j.get("validThrough"),"date_posted":_dates(j)[0],"employment_type":_job_type(j)}

def _workable_public(company,search_url,timeout):
    m=re.search(r"apply\.workable\.com/([^/?#]+)",search_url,re.I)
    if not m:return []
    slug=m.group(1);out=[]
    try:payload=json.loads(_get(f"https://www.workable.com/api/accounts/{slug}?details=true",timeout))
    except Exception:payload={}
    for j in payload.get("jobs",[]):
        shortcode=str(j.get("shortcode") or j.get("code") or "");url=j.get("url") or (f"https://apply.workable.com/{slug}/j/{shortcode}" if shortcode else search_url);desc=_plain(str(j.get("description") or j.get("full_description") or ""));loc=", ".join(str(x) for x in (j.get("city"),j.get("state"),j.get("country")) if x)
        out.append({"external_id":f"workable:{slug}:{shortcode or url}","source":"workable","company_key":company,"title":str(j.get("title") or ""),"location":loc or None,"url":url,"original_url":url,"ats_provider":"workable","ats_identifier":slug,"job_id":shortcode or url,"description":desc,"description_complete":bool(desc),"updated_at":j.get("published") or j.get("created_at")})
    body=_get(search_url,timeout);links=[];seen=set()
    for href in re.findall(r'href=[\'"]([^\'"]+)[\'"]',body,re.I):
        url=urljoin(search_url,html.unescape(href))
        if re.search(rf"apply\.workable\.com/{re.escape(slug)}/j/[^/?#]+",url,re.I) and url not in seen:seen.add(url);links.append(url)
    for shortcode in re.findall(r'(?:/j/|%2Fj%2F)([A-Za-z0-9]{6,})',body,re.I):
        url=f"https://apply.workable.com/{slug}/j/{shortcode}"
        if url not in seen:seen.add(url);links.append(url)
    for url in links:
        try:detail=_get(url,timeout)
        except Exception:continue
        j=_jsonld(detail);title=_plain(str(j.get("title") or ""))
        if not title:
            mt=re.search(r"<title>(.*?)</title>",detail,re.I|re.S);title=_plain(mt.group(1)) if mt else ""
        desc=_plain(str(j.get("description") or detail));ident=_identifier(j,url)
        out.append({"external_id":f"workable:{slug}:{ident}","source":"workable","company_key":company,"title":title,"location":_location(j),"url":url,"original_url":url,"ats_provider":"workable","ats_identifier":slug,"job_id":str(ident),"description":desc,"description_complete":bool(desc),"updated_at":j.get("datePosted"),"posted_on":j.get("datePosted"),"valid_through":j.get("validThrough")})
    print(f"Workable / {company}: {len(_dedupe_jobs(out))} jobs discovered from API/board",flush=True);return _dedupe_jobs(out)

def _detail_fallback(company,search_url,timeout):
    low=search_url.lower()
    if not any(x in low for x in ("opportunitydetail","/jobdetail/","/jobs/details/","/apply/")):return []
    body=_get(search_url,timeout);j=_jsonld(body);title=_plain(str(j.get("title") or ""))
    if not title:
        m=re.search(r"<title>(.*?)</title>",body,re.I|re.S);title=_plain(m.group(1)) if m else ""
    text=_plain(str(j.get("description") or body));ident=_identifier(j,search_url);host=urlparse(search_url).netloc
    return [{"external_id":f"career_site:{company}:{ident}","source":"career_site","company_key":company,"title":title,"location":_location(j),"url":search_url,"original_url":search_url,"ats_provider":host,"ats_identifier":host,"job_id":str(ident),"description":text,"description_complete":bool(text),"updated_at":j.get("datePosted"),"posted_on":j.get("datePosted"),"valid_through":j.get("validThrough")}]

def _amazon_public(company,search_url,timeout):
    from urllib.parse import urlencode
    parsed=urlparse(search_url);params={"base_query":"data engineer","loc_query":"United States"};out=[];seen=set();offset=0
    while True:
        url=f"{parsed.scheme or 'https'}://{parsed.netloc or 'www.amazon.jobs'}/en/search?{urlencode({**params,'offset':offset})}"
        try:body=_get(url,timeout)
        except Exception:
            if offset==0:raise
            break
        links=[]
        for href in re.findall(r'href=[\'"]([^\'"]*/(?:en/)?jobs/\d+/[^\'"]+)[\'"]',body,re.I):
            job_url=urljoin(url,html.unescape(href)).split("?")[0]
            if job_url not in seen:seen.add(job_url);links.append(job_url)
        if not links:break
        for job_url in links:
            try:detail=_get(job_url,timeout)
            except Exception:continue
            j=_jsonld(detail);title=_plain(str(j.get("title") or ""))
            if not title:
                m=re.search(r"<h1[^>]*>(.*?)</h1>",detail,re.I|re.S);title=_plain(m.group(1)) if m else ""
            text=_plain(str(j.get("description") or detail));m=re.search(r"/jobs/(\d+)/",job_url);job_id=m.group(1) if m else job_url
            out.append({"external_id":f"amazon:{job_id}","source":"career_site","company_key":company,"title":title,"location":_location(j),"url":job_url,"original_url":job_url,"ats_provider":"amazon_jobs","ats_identifier":"amazon.jobs","job_id":str(job_id),"description":text,"description_complete":bool(text),"updated_at":j.get("datePosted"),"posted_on":j.get("datePosted"),"date_posted":j.get("datePosted"),"employment_type":_job_type(j)})
        if len(links)<10:break
        offset+=10
    return _dedupe_jobs(out)

def fetch_jobs(company: str,search_url: str,job_url_pattern: str,timeout: int=20)->list[dict]:
    """Crawl an employer career source at maximum recall; qualify jobs downstream."""
    if "apply.workable.com/" in search_url.lower():
        try:return _workable_public(company,search_url,timeout)
        except Exception:pass
    if "amazon.jobs/" in search_url.lower():
        try:return _amazon_public(company,search_url,timeout)
        except Exception:pass
    body=_get(search_url,timeout);embedded=[]
    for j in _jobpostings(body):
        title=_plain(str(j.get("title") or ""));desc=_plain(str(j.get("description") or ""));ident=_identifier(j,title);url=_direct_apply_url(j,search_url)
        embedded.append({"external_id":f"career_site:{company}:{ident}","source":"career_site","company_key":company,"title":title,"location":_location(j),"url":url,"original_url":url,"ats_provider":"career_site","ats_identifier":search_url,"job_id":str(ident),"description":desc,"description_complete":bool(desc),"updated_at":j.get("datePosted"),"posted_on":j.get("datePosted"),"valid_through":j.get("validThrough"),"date_posted":_dates(j)[0],"employment_type":_job_type(j),"hiring_organization":_organization(j),"remote":_remote_flag(j),"salary":_salary(j),"structured_skills":_skills(j),"language":_language(j),"industry":_industry(j),"job_benefits":_benefits(j),"structured_responsibilities":_responsibilities(j),"work_hours":_work_hours(j),"occupational_category":_occupational_category(j),**_education_experience(j),**_source_evidence(j,url)})
    hrefs=re.findall(r"href=['\"]([^'\"]+)['\"]",body,re.I);normalized_pattern=job_url_pattern.replace("\\\\","\\");rx=re.compile(normalized_pattern,re.I);links=[];seen=set()
    for href in hrefs:
        url=urljoin(search_url,html.unescape(href))
        if rx.search(url) and url not in seen:seen.add(url);links.append(url)
    if not links and not embedded:
        fallback=_detail_fallback(company,search_url,timeout)
        if fallback:return fallback
    out=list(embedded);embedded_urls={x.get("url") for x in embedded}
    for url in links:
        if url in embedded_urls:continue
        try:detail=_get(url,timeout)
        except Exception:continue
        j=_jsonld(detail);title=_plain(str(j.get("title") or ""))
        if not title:
            m=re.search(r"<title>(.*?)</title>",detail,re.I|re.S);title=_plain(m.group(1)) if m else ""
        text=_plain(str(j.get("description") or detail));ident=_identifier(j,url)
        out.append({"external_id":f"career_site:{company}:{ident}","source":"career_site","company_key":company,"title":title,"location":_location(j),"url":url,"original_url":url,"ats_provider":"career_site","ats_identifier":search_url,"job_id":ident,"description":text,"description_complete":bool(text),"updated_at":j.get("datePosted"),"posted_on":j.get("datePosted"),"valid_through":j.get("validThrough")})
    out=_dedupe_jobs(out);print(f"CareerSite / {company}: {len(out)} jobs discovered; job-family filtering deferred downstream",flush=True);return out

def validate_source(company: str,search_url: str,job_url_pattern: str,timeout: int=12)->dict:
    result={"company":company,"search_url":search_url,"status":"unknown","http_status":None,"error":None}
    try:
        with urlopen(Request(search_url,headers=UA),timeout=timeout) as resp:
            result["http_status"]=getattr(resp,"status",None)
            try:raw=resp.read(250000)
            except IncompleteRead as exc:raw=exc.partial;result["partial_response"]=True
            body=raw.decode("utf-8","replace")
        result["status"]="ok" if result["http_status"] in (None,200) else "http_error";normalized_pattern=job_url_pattern.replace("\\\\","\\");rx=re.compile(normalized_pattern,re.I);hrefs=re.findall(r"href=['\"]([^'\"]+)['\"]",body,re.I);result["matching_job_links"]=sum(1 for h in hrefs if rx.search(urljoin(search_url,html.unescape(h))));result["embedded_jobpostings"]=len(_jobpostings(body));result["discoverable_jobs"]=result["matching_job_links"]+result["embedded_jobpostings"]
    except HTTPError as exc:result["http_status"]=exc.code;result["status"]="broken" if exc.code in (404,410) else "blocked_or_http_error";result["error"]=str(exc)
    except (URLError,TimeoutError,OSError,IncompleteRead) as exc:result["status"]="unreachable";result["error"]=str(exc)
    except re.error as exc:result["status"]="invalid_pattern";result["error"]=str(exc)
    return result
