from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlparse
from app.company_registry import load as load_registry, save as save_registry, upsert, company_key
from app.company_feeders import collect as collect_company_feeders
from app.company_domain_resolver import resolve_company
from app.career_page_resolver import resolve as resolve_career_page
from app.source_registry import load_registry as load_source_registry, save_registry as save_source_registry, learn_from_jobs as learn_sources_from_jobs, learn_career_site

ROOT=Path(__file__).resolve().parents[1]

def _domain(url):
    try:
        host=urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:return None

def build(source_path="data/job_sources.json", registry_path=None):
    """Seed the open-ended employer universe from every configured company source.

    This is intentionally not an allowlist. Broad discovery and future resolvers
    can add companies that do not appear in job_sources.json.
    """
    cfg=json.loads((ROOT/source_path).read_text(encoding="utf-8"))
    registry_path=registry_path or None
    reg=load_registry() if registry_path is None else load_registry(registry_path)
    before=len(reg)
    for provider,units in cfg.items():
        if not isinstance(units,list):continue
        for row in units:
            if not isinstance(row,dict):continue
            company=row.get("company")
            if not company:continue
            url=row.get("careers_url") or row.get("search_url") or row.get("base_url")
            # ATS URLs are useful as known career sources, but are not assumed to
            # be the employer's corporate domain.
            upsert(reg,company,careers_url=url,ats_provider=None if provider=="career_site" else provider,
                   discovered_by="configured_source")
    # Add identity-level companies from authoritative/public universe feeders.
    # These companies still require official-domain/career-page resolution before
    # they become executable job sources.
    feeder_rows,feeder_errors=collect_company_feeders()
    for row in feeder_rows:
        upsert(reg,row.get("company"),discovered_by=row.get("discovered_by"))
        key=company_key(row.get("company") or "")
        if key in reg:
            if row.get("cik"):reg[key]["sec_cik"]=row["cik"]
            if row.get("ticker"):reg[key]["ticker"]=row["ticker"]
            if row.get("fdic_cert"):reg[key]["fdic_cert"]=row["fdic_cert"]
            if row.get("education_id"):reg[key]["education_id"]=row["education_id"]
            if row.get("cms_facility_id"):reg[key]["cms_facility_id"]=row["cms_facility_id"]
            if row.get("state"):reg[key]["state"]=row["state"]
            if row.get("uei"):reg[key]["sam_uei"]=row["uei"]
            if row.get("official_url"):
                from urllib.parse import urlparse
                url=row["official_url"]
                if "://" not in url:url="https://"+url
                host=urlparse(url).netloc.lower()
                if host.startswith("www."):host=host[4:]
                if host:
                    reg[key]["official_url"]=url
                    reg[key]["official_domain"]=host
                    reg[key]["domain_evidence"]="fdic_institutions" if row.get("fdic_cert") else "college_scorecard"
    resolved_domains=0
    # Resolve only evidence-backed domains. Never derive domains by company-name guessing.
    for row in reg.values():
        if row.get("official_domain"):continue
        try:
            resolved=resolve_company(row)
            if resolved:
                row.update({k:v for k,v in resolved.items() if v})
                resolved_domains+=1
        except Exception:
            continue
    resolved_careers=0
    learned_sources=0
    resolution_failures=0
    custom_career_sites=0
    source_registry=load_source_registry()
    for row in reg.values():
        if not row.get("official_domain") or row.get("ats_provider"):continue
        try:
            career=resolve_career_page(row["official_domain"])
            if not career:
                resolution_failures+=1
                continue
            row.update({k:v for k,v in career.items() if v})
            resolved_careers+=1
            if career.get("ats_provider")=="career_site":custom_career_sites+=1
            # Promote the verified career/ATS result through the same registry
            # learner used by broad discovery, so it becomes executable config.
            if career.get("ats_provider")=="career_site":
                if learn_career_site(row.get("company"),career.get("careers_url"),source_registry):
                    learned_sources+=1
            else:
                synthetic={"company":row.get("company"),"company_key":row.get("company"),
                           "source":"official_career_resolver",
                           "original_url":career.get("careers_url")}
                added=learn_sources_from_jobs([synthetic],source_registry)
                learned_sources+=len(added)
        except Exception:
            resolution_failures+=1
            continue
    save_source_registry(source_registry)
    save_registry(reg) if registry_path is None else save_registry(reg,registry_path)
    return {"companies":len(reg),"added":len(reg)-before,"feeder_rows":len(feeder_rows),
            "resolved_domains":resolved_domains,"resolved_careers":resolved_careers,
            "learned_sources":learned_sources,"custom_career_sites":custom_career_sites,
            "resolution_failures":resolution_failures,"feeder_errors":feeder_errors}

if __name__=="__main__":
    print(json.dumps(build(),indent=2))
