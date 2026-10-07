from __future__ import annotations

from urllib.parse import urlparse

from app.source_registry import detect_ats
from app.sources.greenhouse import fetch_jobs as greenhouse_jobs
from app.sources.lever import fetch_jobs as lever_jobs
from app.sources.ashby import fetch_jobs as ashby_jobs
from app.sources.smartrecruiters import fetch_jobs as smartrecruiters_jobs
from app.sources.workday import fetch_jobs as workday_jobs
from app.sources.successfactors import fetch_jobs as successfactors_jobs
from app.sources.icims import fetch_jobs as icims_jobs
from app.sources.oracle import fetch_jobs as oracle_jobs
from app.sources.eightfold import fetch_jobs as eightfold_jobs
from app.sources.ukg import fetch_jobs as ukg_jobs
from app.sources.adp_workforce_now import fetch_jobs as adp_jobs
from app.sources.avature import fetch_jobs as avature_jobs
from app.sources.phenom import fetch_jobs as phenom_jobs
from app.sources.paylocity import fetch_jobs as paylocity_jobs
from app.sources.workable import fetch_jobs as workable_jobs
from app.sources.jazzhr import fetch_jobs as jazzhr_jobs
from app.sources.dayforce import fetch_jobs as dayforce_jobs
from app.sources.gem import fetch_jobs as gem_jobs
from app.sources.cornerstone import fetch_jobs as cornerstone_jobs
from app.sources.jobvite import fetch_jobs as jobvite_jobs
from app.sources.talentreef import fetch_jobs as talentreef_jobs
from app.sources.public_ats_board import fetch_jobs as public_ats_jobs

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
        "jazzhr": jazzhr_jobs,
        "jazzhr_alt": jazzhr_jobs,
        "dayforce": dayforce_jobs,
        "gem": gem_jobs,
        "cornerstone": cornerstone_jobs,
        "jobvite": jobvite_jobs,
    }
    collector = dedicated.get(provider)
    if collector:
        return collector(company or provider, url), provider, identifier

    if provider in {"talentreef", "jobappnetwork"}:
        client_id = str(source.get("client_id") or source.get("clientId") or "")
        rows = talentreef_jobs(company or provider, client_id, search_url=url)
        for row in rows:
            row["source"] = provider
            row["ats_provider"] = provider
        return rows, provider, identifier

    pattern = source.get("job_url_pattern", r".+")
    return public_ats_jobs(company or provider, url, provider, pattern), provider, identifier
