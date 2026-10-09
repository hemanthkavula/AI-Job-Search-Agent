from __future__ import annotations
import html, json, re
from urllib.parse import urlparse, urlencode, quote
from urllib.request import Request, urlopen

UA={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/plain,*/*"}

TITLE_RE=re.compile(r"\b(data (?:engineer|engineering|platform|infrastructure|pipeline)|big data engineer|etl engineer|analytics engineer|database engineer)\b",re.I)

def _get(url: str, timeout: int = 20) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _plain(value: str) -> str:
    """Normalize actual HTML markup and whitespace in Oracle job text."""
    value=html.unescape(str(value or ""))
    value=re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value=re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()

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
    # Oracle documents recruitingCEJobRequisitions under the versioned HCM REST
    # resources namespace. Finder variables belong inside the finder value.
    finder_values={
        "siteNumber":site,
        "limit":str(limit),
        "offset":str(page*limit),
        "keyword":f'"{keyword}"',
    }
    finder="findReqs;"+",".join(f"{key}={value}" for key,value in finder_values.items())
    params={
        "onlyData":"true",
        "expand":"requisitionList.secondaryLocations",
        "finder":finder,
    }
    path="/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    url=api_base.rstrip("/")+path+"?"+urlencode(params)
    try:
        return json.loads(_get(url,timeout))
    except Exception as exc:
        raise RuntimeError(f"Oracle search failed url={url}: {type(exc).__name__}:{exc}") from exc

def _job_url(base_url: str, row: dict) -> str:
    ident=str(row.get("id") or row.get("requisitionId") or row.get("requisitionNumber") or "")
    lang=str(row.get("contentLocale") or "en")
    return f"{base_url.rstrip('/')}/job/{ident}" if ident else f"{base_url.rstrip('/')}/requisitions"


def _detail_url_parts(url: str) -> tuple[str, str, str] | None:
    """Return Candidate Experience base URL, public site slug, and exact job id.

    Oracle CE can be exposed on the standard oraclecloud path or behind a
    branded employer domain such as /en/sites/CX_1/job/72173.
    """
    parsed=urlparse(url or "")
    path=parsed.path or ""
    patterns=(
        r"(/hcmUI/CandidateExperience/[^/]+/sites/([^/]+))/job/([^/?#]+)",
        r"(/[^/]+/sites/([^/]+))/job/([^/?#]+)",
    )
    match=None
    for pattern in patterns:
        match=re.search(pattern,path,re.I)
        if match:
            break
    if not match:
        return None
    origin=f"{parsed.scheme}://{parsed.netloc}"
    return origin+match.group(1), match.group(2), match.group(3)


def _detail_payload(api_base: str, job_id: str, timeout: int) -> dict:
    """Fetch the external-candidate requisition detail instead of the short search blurb."""
    resource="/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetailsPreviews"
    ident=quote(str(job_id),safe="")
    urls=[
        f"{api_base.rstrip('/')}{resource}/{ident}?onlyData=true",
        f"{api_base.rstrip('/')}{resource}?onlyData=true&q="+quote(f"RequisitionId={job_id}",safe="=()'"),
    ]
    last_error=None
    for url in urls:
        try:
            payload=json.loads(_get(url,timeout))
        except Exception as exc:
            last_error=exc
            continue
        if isinstance(payload,dict):
            items=payload.get("items")
            if isinstance(items,list) and items and isinstance(items[0],dict):
                return items[0]
            # Item endpoints return the requisition object directly.
            if any(payload.get(k) for k in (
                "ExternalDescriptionStr","ExternalResponsibilitiesStr","ExternalQualificationsStr",
                "Title","RequisitionId","ShortDescriptionStr",
            )):
                return payload
    if last_error:
        raise RuntimeError(f"Oracle exact job detail failed: {type(last_error).__name__}:{last_error}")
    return {}


def _full_description(row: dict) -> tuple[str, bool]:
    sections=[]
    values=(
        ("Summary",row.get("ShortDescriptionStr") or row.get("ShortDescription")),
        ("Description",row.get("ExternalDescriptionStr") or row.get("ExternalDescription")),
        ("Responsibilities",row.get("ExternalResponsibilitiesStr") or row.get("ExternalResponsibilities")),
        ("Qualifications",row.get("ExternalQualificationsStr") or row.get("ExternalQualifications")),
    )
    seen=set()
    strong_sections=0
    for label,value in values:
        text=_plain(str(value or ""))
        key=text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        if label in {"Description","Responsibilities","Qualifications"} and len(text)>=80:
            strong_sections+=1
        sections.append(f"{label}: {text}" if label!="Summary" else text)
    description="\n\n".join(sections).strip()
    complete=len(description)>=500 and strong_sections>=2
    return description,complete



def _page_metadata_partial_job(company: str, url: str, public_job_id: str, timeout: int) -> dict | None:
    """Exact Oracle job metadata fallback; an og:description excerpt is NEVER a full JD."""
    try:
        page=_get(url,timeout)
    except Exception:
        return None
    def meta(key: str) -> str:
        match=re.search(r"""<meta\s+[^>]*(?:name|property)=["']"""+re.escape(key)+r"""["'][^>]*content=["']([^"']*)""",page,re.I)
        return html.unescape(match.group(1)).strip() if match else ""
    title=_plain(meta("og:title"))
    desc=_plain(meta("og:description"))
    org=_plain(meta("og:site_name")) or company
    if not title or len(desc)<250 or not any(term in desc.lower() for term in ("data","engineer","analytics","responsibilities","experience","sql")):
        return None
    return {
        "external_id":f"oracle:{org}:{public_job_id}",
        "source":"oracle","company_key":org,"company":org,"title":title,
        "url":url,"original_url":url,"ats_provider":"oracle",
        "job_id":public_job_id,"requisition_id":public_job_id,
        "description":desc,"description_complete":False,
        "exact_job_metadata_source":"oracle_exact_page_og_partial",
    }


def fetch_job(company: str, url: str, timeout: int = 20) -> dict | None:
    """Resolve one Oracle Recruiting Cloud detail URL through Oracle's exact-detail API."""
    parts=_detail_url_parts(url)
    if not parts:
        return None
    base_url,site_slug,public_job_id=parts

    # Branded Oracle Candidate Experience domains do not always expose the
    # data-sitenumber/data-apibaseurl attributes used by the standard shell.
    # The site slug is still present in the public job URL, and on standard
    # oraclecloud hosts the REST API lives on the same origin, so keep a
    # provider-native fallback instead of abandoning exact-job resolution.
    parsed=urlparse(url or "")
    site_number=site_slug
    api_base=f"{parsed.scheme}://{parsed.netloc}"
    try:
        configured_site,configured_api=_page_config(base_url,timeout)
        site_number=configured_site or site_number
        api_base=configured_api or api_base
    except Exception:
        pass
    try:
        row=_detail_payload(api_base,public_job_id,timeout)
    except Exception:
        return _page_metadata_partial_job(company,url,public_job_id,timeout)
    if not row:
        return _page_metadata_partial_job(company,url,public_job_id,timeout)
    description,complete=_full_description(row)
    title=_plain(str(row.get("Title") or row.get("OtherRequisitionTitle") or row.get("RequisitionTitle") or ""))
    if not title or len(description)<180:
        return None
    requisition_id=str(row.get("RequisitionId") or row.get("Id") or public_job_id)
    location=_plain(str(row.get("PrimaryLocation") or row.get("Location") or ""))
    return {
        "external_id":f"oracle:{company}:{requisition_id}",
        "source":"oracle",
        "company_key":company,
        "title":title,
        "location":location or None,
        "url":url,
        "original_url":url,
        "ats_provider":"oracle",
        "ats_identifier":base_url,
        "ats_tenant":site_slug,
        "site_number":site_number,
        "job_id":requisition_id,
        "requisition_id":requisition_id,
        "employment_type":row.get("WorkerType") or row.get("ContractType"),
        "posted_at":row.get("ExternalPostedStartDate"),
        "updated_at":row.get("ExternalPostedStartDate") or row.get("ExternalPostedEndDate"),
        "description":description,
        "description_complete":bool(complete),
        "exact_job_metadata_source":"oracle_exact_api",
    }


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
