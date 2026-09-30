from __future__ import annotations
import re
from urllib.parse import urljoin
from app.sources.career_site import fetch_jobs as _generic, _get, _plain, _jsonld, _location, _job_type

JOB_DETAIL_PATTERNS={
    "bamboohr":r"/careers/(?:\d+|[^/?#]+)",
    "recruitee":r"/o/[^/?#]+",
    "teamtailor":r"/jobs/\d+[^/?#]*",
    "breezyhr":r"/p/[^/?#]+",
    "pinpoint":r"/(?:postings|jobs)/[^/?#]+",
    "careerplug":r"/jobs/\d+",
    "freshteam":r"/jobs/[^/?#]+",
    "jobscore":r"/jobs?/[^/?#]+",
    "personio":r"/job/(?:\d+|[^/?#]+)",
    "comeet":r"/jobs/[^/?#]+/[^/?#]+",
    "applicantpro":r"/jobs/\d+",
    "hirebridge":r"JobDetails\.aspx.*(?:jid|jobid)=",
    "join":r"/companies/[^/?#]+/jobs/[^/?#]+",
    "hireology":r"/jobs/\d+",
    "paycor":r"JobIntroduction\.action.*(?:jobId|jobid)=",
    "peopleadmin":r"/postings/\d+",
    "pageup":r"/cw/(?:en-us/)?job/\d+",
    "applicantstack":r"/x/detail/[^/?#]+",
    "taleo":r"/jobdetail\.ftl.*(?:job|jobid)=",
    "paycom":r"web\.php/jobs/ViewJobDetails.*(?:job|jobid)=",
    "saashr":r"/ta/[^/?#]+\.careers.*jobid=",
    "njoyn":r"(?:clid|jobid)=",
    "recruitcrm":r"/jobs?/[^/?#]+",
}

def _job_pattern(provider: str, configured: str) -> str:
    """Return a job-detail regex instead of crawling every navigation link."""
    if configured and configured not in {r".+", ".+"}:
        return configured
    return JOB_DETAIL_PATTERNS.get(provider, r"(?:/jobs?|/positions?|/postings?|/openings?)/[^/?#]+")

def _rippling(company: str, search_url: str) -> list[dict]:
    """Crawl the complete visible Rippling employer board.

    Discovery maximizes recall; centralized qualification decides job family and
    eligibility after authoritative job details have been collected.
    """
    body=_get(search_url)
    base=re.match(r"(https?://ats\.rippling\.com/(?:[a-z]{2}-[A-Z]{2}/)?[^/?#]+/jobs)",search_url,re.I)
    board=base.group(1) if base else search_url.rstrip("/")
    links=[];seen=set()
    for href in re.findall(r'href=[\'"]([^\'"]+)[\'"]',body,re.I):
        url=urljoin(board+"/",href)
        if re.search(r"ats\.rippling\.com/(?:[a-z]{2}-[A-Z]{2}/)?[^/?#]+/jobs/[0-9a-f-]{20,}",url,re.I) and url not in seen:
            seen.add(url);links.append(url)
    for job_id in re.findall(r"(?:/jobs/|%2Fjobs%2F)([0-9a-f]{8}-[0-9a-f-]{20,})",body,re.I):
        url=board+"/"+job_id
        if url not in seen:
            seen.add(url);links.append(url)
    out=[]
    for url in links:
        try: detail=_get(url)
        except Exception: continue
        j=_jsonld(detail)
        title=_plain(str(j.get("title") or ""))
        if not title:
            m=re.search(r"<h1[^>]*>(.*?)</h1>",detail,re.I|re.S) or re.search(r"<title>(.*?)</title>",detail,re.I|re.S)
            title=_plain(m.group(1)) if m else ""
        text=_plain(str(j.get("description") or detail))
        job_id=url.rstrip("/").rsplit("/",1)[-1]
        out.append({"external_id":f"rippling:{board}:{job_id}","source":"rippling","source_family":"direct_ats_public_board",
                    "company_key":company,"title":title,"location":_location(j),"employment_type":_job_type(j),
                    "url":url,"original_url":url,"ats_provider":"rippling","ats_identifier":board,
                    "job_id":job_id,"description":text,"description_complete":bool(text),
                    "updated_at":j.get("datePosted"),"posted_on":j.get("datePosted"),"date_posted":j.get("datePosted")})
    print(f"Rippling / {company}: {len(out)} jobs discovered from {len(links)} detail links",flush=True)
    return out

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
