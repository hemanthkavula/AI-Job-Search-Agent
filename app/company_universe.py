from __future__ import annotations
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from app.company_registry import load as load_registry, save as save_registry, upsert, company_key
from app.company_feeders import collect as collect_company_feeders
from app.company_domain_resolver import resolve_company, can_resolve_company
from app.career_page_resolver import resolve as resolve_career_page
from app.ats_tenant_resolver import resolve as resolve_ats_tenant
from app.source_registry import load_registry as load_source_registry, save_registry as save_source_registry, learn_resolved_source

ROOT=Path(__file__).resolve().parents[1]
DOMAIN_RESOLVER_VERSION="2026-09-27-v7"
CAREER_RESOLVER_VERSION="2026-09-27-v6"
ATS_TENANT_RESOLVER_VERSION="2026-09-27-v2"

def _domain(url):
    try:
        host=urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:return None

def _retry_due(row, prefix, retry_days, resolver_version=None):
    if resolver_version and row.get(f"{prefix}_resolver_version") != resolver_version:return True
    last=row.get(f"{prefix}_last_attempt_at")
    if not last:return True
    try:
        attempted=datetime.fromisoformat(last.replace("Z","+00:00"))
        return datetime.now(timezone.utc)-attempted >= timedelta(days=retry_days)
    except Exception:return True

def build(source_path="data/job_sources.json", registry_path=None, domain_budget=250, career_budget=250, retry_days=7):
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
            # A configured direct career_site URL is first-party corporate evidence:
            # unlike an ATS-hosted URL, its host can safely seed the verified domain.
            direct_domain=_domain(url) if provider=="career_site" and url else None
            upsert(reg,company,official_domain=direct_domain,careers_url=url,
                   ats_provider=None if provider=="career_site" else provider,
                   discovered_by="configured_source")
            if direct_domain:
                key=company_key(company)
                reg[key]["official_url"]=url
                reg[key]["domain_evidence"]="configured_direct_career_site"
    # Add identity-level companies from authoritative/public universe feeders.
    # data/company_feeders.json is the control plane: only explicitly enabled
    # implemented feeder IDs are executed. Internal seed/learning entries are
    # handled above/by normal discovery and are not external feeder functions.
    feeder_cfg_path=ROOT/"data/company_feeders.json"
    enabled_feeders=None
    if feeder_cfg_path.exists():
        feeder_cfg=json.loads(feeder_cfg_path.read_text(encoding="utf-8"))
        enabled_feeders=[
            row.get("id") for row in feeder_cfg.get("feeders",[])
            if isinstance(row,dict) and row.get("enabled") and row.get("id") in {
                "sec_public_companies","dol_h1b_employers","fdic_insured_banks","ncua_active_credit_unions",
                "college_scorecard_institutions","cms_hospitals","sam_registered_entities"
            }
        ]
    feeder_rows,feeder_errors=collect_company_feeders(enabled_feeders)
    for row in feeder_rows:
        upsert(reg,row.get("company"),discovered_by=row.get("discovered_by"))
        key=company_key(row.get("company") or "")
        if key in reg:
            if row.get("cik"):reg[key]["sec_cik"]=row["cik"]
            if row.get("ticker"):reg[key]["ticker"]=row["ticker"]
            if row.get("fdic_cert"):reg[key]["fdic_cert"]=row["fdic_cert"]
            if row.get("ncua_charter"):reg[key]["ncua_charter"]=row["ncua_charter"]
            if row.get("education_id"):reg[key]["education_id"]=row["education_id"]
            if row.get("cms_facility_id"):reg[key]["cms_facility_id"]=row["cms_facility_id"]
            if row.get("state"):reg[key]["state"]=row["state"]
            if row.get("uei"):reg[key]["sam_uei"]=row["uei"]
            if row.get("recent_h1b_lca"):
                reg[key]["recent_h1b_lca"]=True
                reg[key]["h1b_evidence_source"]=row.get("discovered_by") or "dol_oflc"
            if row.get("official_url"):
                from urllib.parse import urlparse
                url=row["official_url"]
                if "://" not in url:url="https://"+url
                host=urlparse(url).netloc.lower()
                if host.startswith("www."):host=host[4:]
                if host:
                    reg[key]["official_url"]=url
                    reg[key]["official_domain"]=host
                    reg[key]["domain_evidence"]=row.get("discovered_by") or ("fdic_active_institutions" if row.get("fdic_cert") else "authoritative_feeder")
    resolved_domains=0
    domain_attempts=0
    domain_candidates=sorted(
        (r for r in reg.values() if not r.get("official_domain")
         and not (r.get("careers_url") or r.get("ats_provider"))
         and can_resolve_company(r)
         and _retry_due(r,"domain",retry_days,DOMAIN_RESOLVER_VERSION)),
        # Strong authoritative identifiers first; then recent H-1B history.
        # Existing executable sources are excluded above so scarce network budget
        # expands coverage instead of re-enriching already-addressable employers.
        key=lambda r:(not bool(r.get("organization_url_evidence") or r.get("domain_candidate_url") or r.get("official_url")),
                      not bool(r.get("sec_cik")),
                      not bool(r.get("recent_h1b_lca")),
                      bool(r.get("domain_last_attempt_at")),r.get("domain_last_attempt_at") or "")
    )[:domain_budget]
    now=datetime.now(timezone.utc).isoformat()
    for row in domain_candidates:
        row["domain_last_attempt_at"]=now
        row["domain_resolver_version"]=DOMAIN_RESOLVER_VERSION
    domain_attempts=len(domain_candidates)
    # Network-bound resolution is deliberately bounded but concurrent. This turns
    # the budget into useful coverage instead of serially spending minutes on a
    # handful of throttled sites.
    with ThreadPoolExecutor(max_workers=min(24,max(1,domain_attempts))) as pool:
        futures={pool.submit(resolve_company,row):row for row in domain_candidates}
        for future in as_completed(futures):
            row=futures[future]
            try:
                resolved=future.result()
                if resolved:
                    row.update({k:v for k,v in resolved.items() if v})
                    row["domain_last_success_at"]=datetime.now(timezone.utc).isoformat()
                    row.pop("domain_last_error",None)
                    resolved_domains+=1
                else:
                    row["domain_last_error"]="NO_VERIFIED_DOMAIN_EVIDENCE_RETURNED"
            except Exception as e:
                row["domain_last_error"]=f"{type(e).__name__}: {e}"[:500]

    resolved_careers=0
    learned_sources=0
    resolution_failures=0
    custom_career_sites=0
    source_registry=load_source_registry()

    # A corporate domain is useful but must not be a prerequisite for finding a
    # hiring source. Probe a bounded set of unresolved employer identities
    # against public ATS-hosted boards and accept only boards whose exposed
    # organization identity matches the employer.
    # Give domainless employers the same discovery budget as domain resolution.
    # This path can discover an executable ATS source directly and no longer
    # depends on a corporate-domain lookup succeeding first.
    ats_tenant_budget=max(100,domain_budget)
    ats_tenant_candidates=sorted(
        (r for r in reg.values() if not r.get("official_domain")
         and not r.get("ats_provider") and not r.get("careers_url")
         and _retry_due(r,"ats_tenant",retry_days,ATS_TENANT_RESOLVER_VERSION)),
        key=lambda r:(not bool(r.get("recent_h1b_lca")),
                      bool(r.get("ats_tenant_last_attempt_at")),
                      r.get("ats_tenant_last_attempt_at") or "")
    )[:ats_tenant_budget]
    ats_tenant_attempts=len(ats_tenant_candidates)
    ats_tenants_resolved=0
    now=datetime.now(timezone.utc).isoformat()
    for row in ats_tenant_candidates:
        row["ats_tenant_last_attempt_at"]=now
        row["ats_tenant_resolver_version"]=ATS_TENANT_RESOLVER_VERSION
    with ThreadPoolExecutor(max_workers=min(24,max(1,ats_tenant_attempts))) as pool:
        futures={pool.submit(resolve_ats_tenant,row.get("company") or ""):row for row in ats_tenant_candidates}
        for future in as_completed(futures):
            row=futures[future]
            try:
                hit=future.result()
                if not hit:
                    row["ats_tenant_last_error"]="NO_VERIFIED_ATS_TENANT"
                    continue
                row.update({k:v for k,v in hit.items() if v})
                row["ats_tenant_last_success_at"]=datetime.now(timezone.utc).isoformat()
                row.pop("ats_tenant_last_error",None)
                if learn_resolved_source(hit.get("ats_provider"),row.get("company"),
                                         hit.get("careers_url"),source_registry,
                                         identifier=hit.get("ats_identifier")):
                    ats_tenants_resolved+=1
            except Exception as e:
                row["ats_tenant_last_error"]=f"{type(e).__name__}: {e}"[:500]

    career_candidates=sorted(
        (r for r in reg.values() if r.get("official_domain") and not r.get("ats_provider")
         and _retry_due(r,"career",retry_days,CAREER_RESOLVER_VERSION)),
        key=lambda r:(not bool(r.get("recent_h1b_lca")),not bool(r.get("careers_url")),r.get("career_last_attempt_at") or "")
    )[:career_budget]
    career_attempts=len(career_candidates)
    now=datetime.now(timezone.utc).isoformat()
    for row in career_candidates:
        row["career_last_attempt_at"]=now
        row["career_resolver_version"]=CAREER_RESOLVER_VERSION
    with ThreadPoolExecutor(max_workers=min(24,max(1,career_attempts))) as pool:
        futures={pool.submit(resolve_career_page,row["official_domain"]):row for row in career_candidates}
        for future in as_completed(futures):
            row=futures[future]
            try:
                career=future.result()
                if not career:
                    row["career_last_error"]="NO_CAREER_PAGE_RESOLVED"
                    resolution_failures+=1
                    continue
                row.update({k:v for k,v in career.items() if v})
                row["career_last_success_at"]=datetime.now(timezone.utc).isoformat()
                row.pop("career_last_error",None)
                resolved_careers+=1
                if career.get("ats_provider")=="career_site":custom_career_sites+=1
                if learn_resolved_source(
                    career.get("ats_provider"),row.get("company"),career.get("careers_url"),
                    source_registry,identifier=career.get("ats_identifier")
                ):
                    learned_sources+=1
            except Exception as e:
                row["career_last_error"]=f"{type(e).__name__}: {e}"[:500]
                resolution_failures+=1
    save_source_registry(source_registry)
    save_registry(reg) if registry_path is None else save_registry(reg,registry_path)

    # Report cumulative conversion health, not only what changed in this run.
    # This makes sparse ATS families visible and proves whether the open-ended
    # employer universe is actually turning into executable career sources.
    domain_total=sum(bool(r.get("official_domain")) for r in reg.values())
    career_total=sum(bool(r.get("careers_url")) for r in reg.values())
    ats_total=sum(bool(r.get("ats_provider")) for r in reg.values())
    # Coverage denominators must distinguish identity-only records from employers
    # for which we have enough public evidence to address a hiring source.
    addressable_total=sum(bool(r.get("official_domain") or r.get("careers_url") or r.get("ats_provider")) for r in reg.values())
    executable_total=sum(bool(r.get("careers_url") or r.get("ats_provider")) for r in reg.values())
    recent_h1b_total=sum(bool(r.get("recent_h1b_lca")) for r in reg.values())
    ats_by_provider=Counter(
        str(r.get("ats_provider")) for r in reg.values() if r.get("ats_provider")
    )
    executable_by_provider={
        provider:len(rows) for provider,rows in source_registry.items()
        if isinstance(rows,list) and rows
    }
    metrics={"companies":len(reg),"added":len(reg)-before,"feeder_rows":len(feeder_rows),
            "resolved_domains":resolved_domains,"domain_attempts":domain_attempts,"domain_budget":domain_budget,
            "resolved_careers":resolved_careers,"career_attempts":career_attempts,"career_budget":career_budget,
            "learned_sources":learned_sources,"custom_career_sites":custom_career_sites,
            "ats_tenant_attempts":ats_tenant_attempts,"ats_tenant_budget":ats_tenant_budget,
            "ats_tenants_resolved":ats_tenants_resolved,"ats_tenant_resolver_version":ATS_TENANT_RESOLVER_VERSION,
            "resolution_failures":resolution_failures,"retry_days":retry_days,"domain_resolver_version":DOMAIN_RESOLVER_VERSION,"career_resolver_version":CAREER_RESOLVER_VERSION,"feeder_errors":feeder_errors,
            "companies_with_verified_domain":domain_total,
            "companies_with_careers_url":career_total,
            "companies_with_ats_provider":ats_total,
            "companies_with_recent_h1b_lca":recent_h1b_total,
            "identity_only_companies":len(reg)-addressable_total,
            "source_addressable_companies":addressable_total,
            "companies_with_executable_career_source":executable_total,
            "ats_by_provider":dict(sorted(ats_by_provider.items())),
            "executable_learned_sources_by_provider":dict(sorted(executable_by_provider.items())),
            "domain_coverage_pct":round(100*domain_total/len(reg),2) if reg else 0.0,
            "career_coverage_pct":round(100*career_total/len(reg),2) if reg else 0.0,
            "ats_coverage_pct":round(100*ats_total/len(reg),2) if reg else 0.0,
            "actionable_source_coverage_pct":round(100*executable_total/addressable_total,2) if addressable_total else 0.0,
            "career_coverage_of_verified_domains_pct":round(100*career_total/domain_total,2) if domain_total else 0.0,
            "ats_coverage_of_verified_domains_pct":round(100*ats_total/domain_total,2) if domain_total else 0.0,
            "executable_source_coverage_of_verified_domains_pct":round(100*sum(bool(r.get("careers_url") or r.get("ats_provider")) for r in reg.values())/domain_total,2) if domain_total else 0.0}
    print("EMPLOYER_UNIVERSE "+json.dumps(metrics,sort_keys=True),flush=True)
    return metrics

if __name__=="__main__":
    print(json.dumps(build(),indent=2))
