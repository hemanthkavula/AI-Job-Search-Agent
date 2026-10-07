from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

from app.ats_tenant_resolver import resolve as resolve_ats_tenant
from app.career_page_resolver import resolve as resolve_career_page
from app.company_registry import company_key, load as load_company_registry, save as save_company_registry
from app.source_registry import detect_ats, learn_resolved_source, load_registry, save_registry
from app.sources.greenhouse import fetch_jobs as greenhouse_jobs
from app.sources.lever import fetch_jobs as lever_jobs
from app.sources.ashby import fetch_jobs as ashby_jobs
from app.sources.smartrecruiters import fetch_jobs as smartrecruiters_jobs
from app.sources.workable import fetch_jobs as workable_jobs
from app.sources.workday import fetch_jobs as workday_jobs
from app.sources.public_ats_board import fetch_jobs as public_board_jobs

AGGREGATOR_HOSTS=("dice.com","indeed.com","linkedin.com","ziprecruiter.com","monster.com","wellfound.com","builtin.com","ycombinator.com")
CORE_TITLE_STOP={"senior","sr","lead","principal","staff","ii","iii","iv","remote","hybrid","onsite","on","site"}


def _is_aggregator(url):
    try:
        host=(urlparse(str(url or "")).netloc or "").lower()
    except Exception:
        return False
    return any(host==h or host.endswith("."+h) for h in AGGREGATOR_HOSTS)


def _tokens(value):
    return [x for x in re.findall(r"[a-z0-9]+",(value or "").lower()) if x not in CORE_TITLE_STOP]


def _title_score(expected,actual):
    e=_tokens(expected);a=_tokens(actual)
    if not e or not a:return 0.0
    overlap=len(set(e)&set(a))/max(1,len(set(e)))
    seq=SequenceMatcher(None," ".join(e)," ".join(a)).ratio()
    return max(overlap,seq)


def _location_tokens(value):
    stop={"united","states","usa","us","remote","hybrid","onsite","on","site"}
    return {x for x in re.findall(r"[a-z0-9]+",(value or "").lower()) if len(x)>=2 and x not in stop}


def _match_rows(job,rows,provider,identifier=None):
    expected_title=job.get("title") or ""
    expected_location=job.get("location") or ""
    expected_req=str(job.get("requisition_id") or job.get("job_id") or "").strip().lower()
    ranked=[]
    for row in rows or []:
        url=row.get("original_url") or row.get("url")
        if not url or _is_aggregator(url):continue
        title=row.get("title") or ""
        score=_title_score(expected_title,title)
        if score<0.67:continue
        candidate_req=str(row.get("requisition_id") or row.get("job_id") or "").strip().lower()
        if expected_req and candidate_req and expected_req!=candidate_req and expected_req not in candidate_req and candidate_req not in expected_req:
            continue
        loc_bonus=0.0
        et=_location_tokens(expected_location);ct=_location_tokens(row.get("location") or "")
        if et and ct and et&ct:loc_bonus=0.12
        req_bonus=0.20 if expected_req and candidate_req and (expected_req==candidate_req or expected_req in candidate_req or candidate_req in expected_req) else 0.0
        desc_bonus=0.05 if len((row.get("description") or "").strip())>=250 else 0.0
        ranked.append((score+loc_bonus+req_bonus+desc_bonus,row))
    if not ranked:return None
    ranked.sort(key=lambda x:x[0],reverse=True)
    best_score,best=ranked[0]
    # Avoid silently resolving ambiguous boards with several similar roles.
    if len(ranked)>1 and best_score-ranked[1][0]<0.08:
        # A requisition-id match is strong enough to disambiguate otherwise
        # identical titles. Without that evidence, do not guess between multiple
        # live openings carrying the same title/location.
        best_req=str(best.get("requisition_id") or best.get("job_id") or "").strip().lower()
        req_disambiguates=bool(expected_req and best_req and (expected_req==best_req or expected_req in best_req or best_req in expected_req))
        if not req_disambiguates:return None
    out=dict(best)
    out["ats_provider"]=provider
    out["ats_identifier"]=identifier or out.get("ats_identifier")
    out["ats_resolution"]="verified_employer_source_match"
    out["resolver_match_score"]=round(best_score,3)
    return out


def _workday_parts(url,identifier):
    host=(urlparse(url or "").netloc or "").lower()
    tenant=None;site=None
    if identifier and "|" in str(identifier):
        tenant,site=str(identifier).split("|",1)
    if (not tenant or not site) and url:
        provider,detected=detect_ats(url)
        if provider=="workday" and detected and "|" in detected:
            tenant,site=detected.split("|",1)
    if not tenant and host:tenant=host.split(".",1)[0]
    return host,tenant,site


def _fetch_rows(company,hit):
    provider=(hit.get("ats_provider") or "").lower()
    url=hit.get("careers_url") or hit.get("search_url") or hit.get("original_url") or ""
    identifier=hit.get("ats_identifier") or hit.get("identifier")
    if not provider and url:
        provider,detected=detect_ats(url)
        identifier=identifier or detected
    if not provider or not url:return [],provider,identifier
    try:
        if provider=="greenhouse":
            token=identifier or detect_ats(url)[1]
            return greenhouse_jobs(token),provider,token
        if provider=="lever":
            site=identifier or detect_ats(url)[1]
            return lever_jobs(site),provider,site
        if provider=="ashby":
            board=identifier or detect_ats(url)[1]
            return ashby_jobs(board),provider,board
        if provider=="smartrecruiters":
            ident=identifier or detect_ats(url)[1]
            return smartrecruiters_jobs(ident,hours=48),provider,ident
        if provider=="workable":
            return workable_jobs(company,url),provider,identifier or detect_ats(url)[1]
        if provider=="workday":
            host,tenant,site=_workday_parts(url,identifier)
            if host and tenant and site:
                return workday_jobs(company,host,tenant,site,hours=48),provider,f"{tenant}|{site}"
            return [],provider,identifier
        # Long-tail public ATS boards already share the generic evidence-aware
        # collector used by production discovery.
        return public_board_jobs(company,url,provider),provider,identifier or detect_ats(url)[1]
    except Exception:
        return [],provider,identifier


def _source_registry_hits(company,registry):
    key=company_key(company)
    out=[]
    for provider,rows in (registry or {}).items():
        if not isinstance(rows,list):continue
        for row in rows:
            if company_key((row or {}).get("company") or "")!=key:continue
            url=(row.get("search_url") or row.get("base_url") or row.get("original_url") or row.get("url") or row.get("careers_url"))
            if not url or _is_aggregator(url):continue
            ident=(row.get("identifier") or row.get("board_token") or row.get("site") or row.get("board_name") or row.get("company_identifier"))
            out.append({"careers_url":url,"ats_provider":provider,"ats_identifier":ident,"evidence":"source_registry"})
    return out


def _candidate_sources(job):
    company=(job.get("company_key") or job.get("company") or "").strip()
    if not company:return []
    out=[]
    seen=set()
    company_registry=load_company_registry()
    company_row=company_registry.get(company_key(company)) or {}
    source_registry=load_registry()

    def add(hit):
        if not isinstance(hit,dict):return
        url=hit.get("careers_url") or hit.get("search_url") or hit.get("original_url")
        if not url or _is_aggregator(url):return
        provider=hit.get("ats_provider")
        ident=hit.get("ats_identifier")
        if not provider:
            provider,detected=detect_ats(url);ident=ident or detected
        if not provider:return
        sig=(provider,str(ident or ""),str(url).rstrip("/"))
        if sig in seen:return
        seen.add(sig)
        out.append({"careers_url":url,"ats_provider":provider,"ats_identifier":ident,"evidence":hit.get("evidence") or hit.get("ats_evidence")})

    # 1) Previously verified executable sources are cheapest and strongest.
    for hit in _source_registry_hits(company,source_registry):add(hit)

    # 2) Canonical company registry evidence.
    careers=company_row.get("careers_url")
    if careers and not _is_aggregator(careers):
        add({"careers_url":careers,"ats_provider":company_row.get("ats_provider"),"ats_identifier":company_row.get("ats_identifier"),"evidence":"company_registry"})
    direct_site=job.get("employer_website")
    official_domain=company_row.get("official_domain") or direct_site
    if official_domain:
        try:add(resolve_career_page(official_domain))
        except Exception:pass

    # 3) Domainless employers can still be found on hosted ATS boards. In
    # production the discovery stage has already registered the employer as a
    # current hiring signal. Gate this network-heavy fallback on that evidence so
    # isolated unit/diagnostic calls do not unexpectedly perform public searches.
    if company_row and (company_row.get("current_hiring_signal") or company_row.get("ats_resolution_pending")):
        try:add(resolve_ats_tenant(company))
        except Exception:pass
    return out


def _persist_resolution(company,hit,matched):
    url=matched.get("original_url") or matched.get("url")
    provider=matched.get("ats_provider") or hit.get("ats_provider")
    identifier=matched.get("ats_identifier") or hit.get("ats_identifier")
    if not company or not url or not provider:return
    try:
        registry=load_registry()
        learn_resolved_source(provider,company,hit.get("careers_url") or url,registry,identifier=identifier,learned_from="aggregator_job_resolution")
        save_registry(registry)
    except Exception:
        pass
    try:
        reg=load_company_registry()
        row=reg.setdefault(company_key(company),{"company":company})
        row.update({"company":company,"careers_url":hit.get("careers_url") or url,"ats_provider":provider,"ats_identifier":identifier})
        save_company_registry(reg)
    except Exception:
        pass


def resolve(job):
    """Resolve a board lead to the exact job on a verified employer ATS source."""
    company=(job.get("company_key") or job.get("company") or "").strip()
    for hit in _candidate_sources(job):
        rows,provider,identifier=_fetch_rows(company,hit)
        matched=_match_rows(job,rows,provider,identifier)
        if matched:
            # Keep the original employer identity rather than provider tenant slugs.
            matched["company_key"]=company
            matched["aggregator_url"]=job.get("aggregator_url") or job.get("url")
            matched["discovery_source"]=job.get("source")
            _persist_resolution(company,hit,matched)
            return matched
    return None
