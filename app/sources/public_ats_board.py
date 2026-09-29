from __future__ import annotations
import re
from urllib.parse import urljoin
from app.sources.career_site import fetch_jobs as _generic, _get, _plain, _jsonld, _location, _job_type

DE_TERMS=("data engineer","data engineering","data platform engineer","data infrastructure engineer","data pipeline engineer","big data engineer","etl engineer","analytics engineer","data & analytics engineer")

\nJOB_DETAIL_PATTERNS={\n    "bamboohr":r"/careers/(?:\\d+|[^/?#]+)",\n    "recruitee":r"/o/[^/?#]+",\n    "teamtailor":r"/jobs/\\d+[^/?#]*",\n    "breezyhr":r"/p/[^/?#]+",\n    "pinpoint":r"/(?:postings|jobs)/[^/?#]+",\n    "careerplug":r"/jobs/\\d+",\n    "freshteam":r"/jobs/[^/?#]+",\n    "jobscore":r"/jobs?/[^/?#]+",\n    "personio":r"/job/(?:\\d+|[^/?#]+)",\n    "comeet":r"/jobs/[^/?#]+/[^/?#]+",\n    "applicantpro":r"/jobs/\\d+",\n    "hirebridge":r"JobDetails\\.aspx.*(?:jid|jobid)=",\n    "join":r"/companies/[^/?#]+/jobs/[^/?#]+",\n    "hireology":r"/jobs/\\d+",\n    "paycor":r"JobIntroduction\\.action.*(?:jobId|jobid)=",\n    "peopleadmin":r"/postings/\\d+",\n    "pageup":r"/cw/(?:en-us/)?job/\\d+",\n    "applicantstack":r"/x/detail/[^/?#]+",\n    "taleo":r"/jobdetail\\.ftl.*(?:job|jobid)=",\n    "paycom":r"web\\.php/jobs/ViewJobDetails.*(?:job|jobid)=",\n    "saashr":r"/ta/[^/?#]+\\.careers.*jobid=",\n    "njoyn":r"(?:clid|jobid)=",\n    "recruitcrm":r"/jobs?/[^/?#]+",\n}\n\ndef _job_pattern(provider: str, configured: str) -> str:\n    """Return a job-detail regex instead of crawling every navigation link."""\n    if configured and configured not in {r".+", ".+"}:\n        return configured\n    return JOB_DETAIL_PATTERNS.get(provider, r"(?:/jobs?|/positions?|/postings?|/openings?)/[^/?#]+")\n\ndef _rippling(company: str, search_url: str) -> list[dict]:
    """Crawl a Rippling employer board by tenant, then resolve matching job details.

    Rippling boards expose ordinary /<tenant>/jobs/<uuid> links in the public board
    HTML. Reading the board rather than a single discovered detail URL makes the
    tenant reusable for every future posting.
    """
    body=_get(search_url)
    base=re.match(r"(https?://ats\.rippling\.com/(?:[a-z]{2}-[A-Z]{2}/)?[^/?#]+/jobs)",search_url,re.I)
    board=base.group(1) if base else search_url.rstrip("/")
    links=[];seen=set()
    tenant_path=re.escape(re.sub(r"^https?://ats\.rippling\.com/","",board,flags=re.I).rstrip("/"))
    for href in re.findall(r'href=[\'"]([^\'"]+)[\'"]',body,re.I):
        url=urljoin(board+"/",href)
        if re.search(rf"ats\.rippling\.com/(?:[a-z]{{2}}-[A-Z]{{2}}/)?[^/?#]+/jobs/[0-9a-f-]{{20,}}",url,re.I) and url not in seen:
            seen.add(url);links.append(url)
    # Some Rippling board renders include detail URLs in serialized state rather
    # than anchor tags. Recover UUIDs without depending on a particular locale.
    for job_id in re.findall(r"(?:/jobs/|%2Fjobs%2F)([0-9a-f]{8}-[0-9a-f-]{20,})",body,re.I):
        url=board+"/"+job_id
        if url not in seen:
            seen.add(url);links.append(url)
    out=[]
    for url in links[:500]:
        try: detail=_get(url)
        except Exception: continue
        j=_jsonld(detail)
        title=_plain(str(j.get("title") or ""))
        if not title:
            m=re.search(r"<h1[^>]*>(.*?)</h1>",detail,re.I|re.S) or re.search(r"<title>(.*?)</title>",detail,re.I|re.S)
            title=_plain(m.group(1)) if m else ""
        text=_plain(str(j.get("description") or detail))
        hay=(title+" "+text[:4000]).lower()
        if not any(term in hay for term in DE_TERMS): continue
        job_id=url.rstrip("/").rsplit("/",1)[-1]
        out.append({"external_id":f"rippling:{board}:{job_id}","source":"rippling","source_family":"direct_ats_public_board",
                    "company_key":company,"title":title,"location":_location(j),"employment_type":_job_type(j),
                    "url":url,"original_url":url,"ats_provider":"rippling","ats_identifier":board,
                    "job_id":job_id,"description":text,"description_complete":bool(text),
                    "updated_at":j.get("datePosted"),"posted_on":j.get("datePosted"),"date_posted":j.get("datePosted")})
    return out

# Public-board collector for ATS products whose employer boards expose normal
# HTML/JSON-LD job pages. Provider-specific board crawlers can live here until
# they become large enough for their own module.
def fetch_jobs(company: str, search_url: str, provider: str, job_url_pattern: str = r".+") -> list[dict]:
    if provider=="rippling" and "ats.rippling.com/" in (search_url or "").lower():
        rows=_rippling(company,search_url)
    else:
        rows=_generic(company,search_url,_job_pattern(provider,job_url_pattern))
    for row in rows:
        row["source"]=provider
        row["source_family"]="direct_ats_public_board"
        row["ats_provider"]=provider
    return rows
