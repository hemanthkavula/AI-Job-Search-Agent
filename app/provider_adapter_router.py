from __future__ import annotations

import html
import json
import re
from urllib.parse import urlparse

from app.source_registry import detect_ats, reusable_search_url
from app.sources.career_site import _get as public_get, _jobpostings, _plain
from app.sources.greenhouse import fetch_jobs as greenhouse_jobs
from app.sources.lever import fetch_job as lever_job, fetch_jobs as lever_jobs
from app.sources.ashby import fetch_jobs as ashby_jobs
from app.sources.smartrecruiters import fetch_jobs as smartrecruiters_jobs
from app.sources.workday import fetch_jobs as workday_jobs
from app.sources.successfactors import fetch_jobs as successfactors_jobs
from app.sources.icims import fetch_jobs as icims_jobs
from app.sources.oracle import fetch_job as oracle_job, fetch_jobs as oracle_jobs
from app.sources.eightfold import fetch_job as eightfold_job, fetch_jobs as eightfold_jobs
from app.sources.ukg import fetch_job as ukg_job, fetch_jobs as ukg_jobs
from app.sources.adp_workforce_now import fetch_jobs as adp_jobs
from app.sources.avature import fetch_jobs as avature_jobs
from app.sources.phenom import fetch_jobs as phenom_jobs
from app.sources.paylocity import fetch_job as paylocity_job, fetch_jobs as paylocity_jobs
from app.sources.workable import fetch_job as workable_job, fetch_jobs as workable_jobs
from app.sources.jazzhr import fetch_jobs as jazzhr_jobs
from app.sources.dayforce import fetch_jobs as dayforce_jobs
from app.sources.gem import fetch_jobs as gem_jobs
from app.sources.cornerstone import fetch_jobs as cornerstone_jobs
from app.sources.jobvite import fetch_jobs as jobvite_jobs
from app.sources.talentreef import fetch_jobs as talentreef_jobs
from app.sources.public_ats_board import fetch_jobs as public_ats_jobs
from app.sources.bamboohr import fetch_job as bamboohr_job, fetch_jobs as bamboohr_jobs
from app.sources.zoho_recruit import fetch_job as zoho_recruit_job
from app.sources.taleo import fetch_job as taleo_job

_URL_FIELDS = ("careers_url", "search_url", "base_url", "original_url", "url")


def source_url(source: dict) -> str:
    for key in _URL_FIELDS:
        value = source.get(key)
        if value:
            return str(value)
    return ""


def detected_source(url: str, provider: str | None = None, identifier: str | None = None) -> tuple[str | None, str | None]:
    detected_provider, detected_identifier = detect_ats(url)
    return provider or detected_provider, identifier or detected_identifier


_TITLE_KEYS=("posting_name","postingName","jobTitle","job_title","positionTitle","position_title","title","name")
_DESC_KEYS=("job_description","jobDescription","descriptionHtml","description_html","description","content")
_URL_KEYS=("canonicalPositionUrl","canonicalUrl","jobUrl","job_url","applyUrl","apply_url","url")
_ID_KEYS=("ats_job_id","display_job_id","jobPostingId","jobId","job_id","requisitionId","requisition_id","id")


def _first_text(node: dict, keys) -> str:
    for key in keys:
        value=node.get(key)
        if isinstance(value,(str,int,float)) and str(value).strip():
            return str(value).strip()
    return ""


def _company_text(node: dict, fallback: str) -> str:
    for key in ("hiringOrganization","company","companyName","company_name","organization"):
        value=node.get(key)
        if isinstance(value,dict):
            value=value.get("name") or value.get("legalName") or value.get("displayName")
        if isinstance(value,str) and value.strip():
            return _plain(value)
    return fallback


def _location_text(node: dict) -> str:
    value=next((node.get(k) for k in ("location","locations","jobLocation","formattedLocation","locationName") if node.get(k)),None)
    if isinstance(value,str):
        return _plain(value)
    if isinstance(value,dict):
        address=value.get("address") if isinstance(value.get("address"),dict) else value
        return ", ".join(str(address.get(k)).strip() for k in ("addressLocality","addressRegion","addressCountry","city","state","country") if address.get(k))
    if isinstance(value,list):
        parts=[]
        for item in value:
            if isinstance(item,str):parts.append(_plain(item))
            elif isinstance(item,dict):
                text=_location_text({"location":item})
                if text:parts.append(text)
        return " | ".join(dict.fromkeys(x for x in parts if x))
    return ""


def _normalize_candidate(node: dict, page_url: str, company: str, provider: str | None, identifier: str | None) -> dict | None:
    if not isinstance(node,dict):return None
    title=_plain(_first_text(node,_TITLE_KEYS))
    desc=_plain(_first_text(node,_DESC_KEYS))
    if not title or len(desc)<180 or len(title)>220:return None
    job_url=_first_text(node,_URL_KEYS) or page_url
    ident=_first_text(node,_ID_KEYS)
    employment=node.get("employmentType") or node.get("timeType") or node.get("workerType")
    posted=node.get("datePosted") or node.get("postedOn") or node.get("postedDate") or node.get("createdDate")
    return {
        "external_id":f"{provider or 'ats'}:{company}:{ident or job_url}",
        "source":provider or "ats",
        "company_key":_company_text(node,company) or company,
        "title":title,
        "location":_location_text(node) or None,
        "url":job_url,
        "original_url":job_url,
        "ats_provider":provider,
        "ats_identifier":identifier,
        "job_id":ident or None,
        "requisition_id":ident or None,
        "employment_type":employment,
        "posted_at":posted,
        "description":desc,
        "description_complete":True,
        "exact_job_metadata_source":"direct_structured_payload",
    }


def _walk_json(node):
    stack=[node]
    while stack:
        value=stack.pop()
        if isinstance(value,dict):
            yield value
            stack.extend(value.values())
        elif isinstance(value,list):
            stack.extend(value)


def _json_payloads(body: str):
    for raw in re.findall(r"<script[^>]*>(.*?)</script>",body or "",re.I|re.S):
        text=html.unescape(raw.strip())
        if not text or text[0] not in "[{":continue
        try:yield json.loads(text)
        except Exception:continue


def _url_key(value: str) -> str:
    try:
        p=urlparse(str(value or ""))
        return ((p.netloc or "").lower()+re.sub(r"/+","/",p.path or "").rstrip("/").lower())
    except Exception:return ""


def _candidate_score(row: dict, target_url: str) -> float:
    score=0.0
    target=_url_key(target_url);actual=_url_key(row.get("original_url") or row.get("url"))
    if target and actual==target:score+=5.0
    ident=str(row.get("requisition_id") or row.get("job_id") or "").strip().lower()
    if ident and len(ident)>=4 and ident in str(target_url or "").lower():score+=3.0
    desc=str(row.get("description") or "")
    if len(desc)>=500:score+=1.0
    if len(desc)>=1500:score+=0.5
    return score


def fetch_exact_job(provider: str | None, company: str, source: dict, *, timeout: int = 25) -> tuple[dict | None, str | None, str | None]:
    """Extract one exact job from a supplied ATS detail URL before any board enumeration."""
    url=source_url(source)
    identifier=source.get("ats_identifier") or source.get("identifier")
    provider,identifier=detected_source(url,provider or source.get("ats_provider"),identifier)
    if not provider or not url:return None,provider,identifier

    # Prefer provider-native exact-job APIs when available. These understand the
    # ATS's own detail endpoint better than generic HTML/JSON parsing.
    exact_fetchers={
        "eightfold": eightfold_job,
        "oracle": oracle_job,
        "lever": lever_job,
        "workable": workable_job,
        "paylocity": paylocity_job,
        "bamboohr": bamboohr_job,
        "zoho_recruit": zoho_recruit_job,
        "taleo": taleo_job,
        "ukg": ukg_job,
        "ultipro": ukg_job,
        "ultipro_ukg": ukg_job,
    }
    exact_fetcher=exact_fetchers.get(provider)
    if exact_fetcher:
        try:
            row=exact_fetcher(company or provider,url,timeout=timeout)
        except Exception:
            row=None
        if row:
            row["ats_provider"]=provider
            row["ats_identifier"]=row.get("ats_identifier") or identifier
            row["exact_job_metadata_source"]=row.get("exact_job_metadata_source") or f"{provider}_exact_api"
            return row,provider,row.get("ats_identifier") or identifier

    # Provider-native exact-detail APIs outrank HTML scraping. They return the
    # same canonical fields used by discovery but do not require the title to be
    # known before resolving the exact job.
    if provider=="eightfold":
        try:
            row=eightfold_job(company,url,timeout)
        except Exception:
            row=None
        if row:
            return row,provider,identifier

    try:body=public_get(url,timeout)
    except Exception:return None,provider,identifier
    candidates=[]
    for node in _jobpostings(body):
        row=_normalize_candidate(node,url,company,provider,identifier)
        if row:candidates.append(row)
    for payload in _json_payloads(body):
        for node in _walk_json(payload):
            row=_normalize_candidate(node,url,company,provider,identifier)
            if row:candidates.append(row)
    if not candidates:return None,provider,identifier
    candidates.sort(key=lambda row:(_candidate_score(row,url),len(row.get("description") or "")),reverse=True)
    best=candidates[0]
    # A direct structured payload on the supplied page is authoritative enough
    # even when the embedded job URL is absent or normalized differently.
    best["url"]=best.get("url") or url
    best["original_url"]=best.get("original_url") or url
    return best,provider,identifier


def _workday_parts(url: str, identifier: str | None) -> tuple[str, str | None, str | None]:
    host = (urlparse(url or "").netloc or "").lower()
    tenant = site = None
    if identifier and "|" in str(identifier):
        tenant, site = str(identifier).split("|", 1)
    if (not tenant or not site) and url:
        provider, detected = detect_ats(url)
        if provider == "workday" and detected and "|" in detected:
            tenant, site = detected.split("|", 1)
    if not tenant and host:
        tenant = host.split(".", 1)[0]
    return host, tenant, site


def fetch_provider_jobs(provider: str | None, company: str, source: dict, *, hours: int = 48) -> tuple[list[dict], str | None, str | None]:
    """Dispatch a detected ATS source through the production provider collector."""
    url = source_url(source)
    identifier = source.get("ats_identifier") or source.get("identifier")
    provider, identifier = detected_source(url, provider or source.get("ats_provider"), identifier)
    if not provider or not url:
        return [], provider, identifier
    board_url=reusable_search_url(provider,url) or url

    if provider == "greenhouse":
        token = source.get("board_token") or identifier
        return (greenhouse_jobs(token), provider, token) if token else ([], provider, identifier)
    if provider == "lever":
        site = source.get("site") or identifier
        return (lever_jobs(site), provider, site) if site else ([], provider, identifier)
    if provider == "ashby":
        board = source.get("board_name") or identifier
        return (ashby_jobs(board), provider, board) if board else ([], provider, identifier)
    if provider == "smartrecruiters":
        ident = source.get("company_identifier") or identifier
        return (smartrecruiters_jobs(ident, hours=hours), provider, ident) if ident else ([], provider, identifier)
    if provider == "workday":
        host = source.get("host")
        tenant = source.get("tenant")
        site = source.get("site")
        if not (host and tenant and site):
            host, tenant, site = _workday_parts(url, identifier)
        if host and tenant and site:
            normalized = f"{tenant}|{site}"
            return workday_jobs(company or tenant, host, tenant, site, source.get("locale", "en-US"), hours=hours), provider, normalized
        return [], provider, identifier

    dedicated = {
        "successfactors": successfactors_jobs,
        "icims": icims_jobs,
        "oracle": oracle_jobs,
        "eightfold": eightfold_jobs,
        "ukg": ukg_jobs,
        "ultipro": ukg_jobs,
        "ultipro_ukg": ukg_jobs,
        "adp_workforce_now": adp_jobs,
        "avature": avature_jobs,
        "phenom": phenom_jobs,
        "paylocity": paylocity_jobs,
        "workable": workable_jobs,
        "bamboohr": bamboohr_jobs,
        "jazzhr": jazzhr_jobs,
        "jazzhr_alt": jazzhr_jobs,
        "dayforce": dayforce_jobs,
        "gem": gem_jobs,
        "cornerstone": cornerstone_jobs,
        "jobvite": jobvite_jobs,
    }
    collector = dedicated.get(provider)
    if collector:
        return collector(company or provider, board_url), provider, identifier

    if provider in {"talentreef", "jobappnetwork"}:
        client_id = str(source.get("client_id") or source.get("clientId") or "")
        rows = talentreef_jobs(company or provider, client_id, search_url=board_url)
        for row in rows:
            row["source"] = provider
            row["ats_provider"] = provider
        return rows, provider, identifier

    pattern = source.get("job_url_pattern", r".+")
    return public_ats_jobs(company or provider, board_url, provider, pattern), provider, identifier
