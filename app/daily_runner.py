from __future__ import annotations
import argparse,json,re
from datetime import datetime,timezone,timedelta
from collections import Counter
from pathlib import Path
from app.config import load_profile
from app.discovery import discover, ALL_ATS_PROVIDERS
from app.freshness import fresh_jobs
from app.filters import passes_hard_filters
from app.eligibility import two_category_filter
from app.job_ledger import load_ledger, save_ledger, seen_or_submitted, record_seen
from app.company_registry import load as load_company_registry, save as save_company_registry, learn_from_jobs as learn_companies_from_jobs
from app.job_identity import identity_keys

ROOT=Path(__file__).resolve().parent.parent

def load_sources(path):return json.loads(Path(path).read_text(encoding="utf-8"))

def _reason_key(reason):
    r=(reason or "").lower()
    if "data-engineering job family" in r or "title/jd outside" in r:return "wrong_job_family"
    if "location outside united states" in r:return "location_outside_us"
    if "employment type outside" in r:return "employment_type_mismatch"
    if "experience requirement" in r:return "experience_mismatch"
    if "sponsorship unavailable" in r:return "no_future_sponsorship"
    if "citizenship required" in r:return "citizenship_restriction"
    if "clearance required" in r:return "clearance_restriction"
    if "excluded prior employer" in r:return "excluded_prior_employer"
    return "other_hard_filter"

def _norm_company(value):
    text=re.sub(r"[^a-z0-9]+"," ",(value or "").lower()).strip()
    text=re.sub(r"\b(incorporated|inc|corp|corporation|llc|ltd|limited|company|co)\b","",text)
    return re.sub(r"\s+"," ",text).strip()

def _norm_title(value):
    text=re.sub(r"\([^)]*\)"," ",(value or "").lower())
    text=re.sub(r"\b(remote|hybrid|on[- ]site|onsite)\b"," ",text)
    text=re.sub(r"[^a-z0-9]+"," ",text)
    return re.sub(r"\s+"," ",text).strip()

SOURCE_PRIORITY={name:0 for name in ALL_ATS_PROVIDERS}
SOURCE_PRIORITY.update({"career_site":1,"dice":2,"ziprecruiter":2})

def _dedup_eligible(items):
    """Prefer official ATS/company sources and use the persistent identity model."""
    kept=[];duplicates=[];seen={}
    items=sorted(items,key=lambda x: SOURCE_PRIORITY.get((x.get("job") or {}).get("source"),1))
    for item in items:
        raw=item["job"]
        keys=identity_keys(raw)
        duplicate=None
        for key in keys:
            if key in seen:
                duplicate=seen[key]
                break
        if duplicate:
            duplicates.append({"job":raw,"duplicate_of":duplicate["job"].get("external_id"),"action":"SKIP_DUPLICATE"})
            continue
        kept.append(item)
        for key in keys:
            seen[key]=item
    return kept,duplicates

def _parse_health_time(value):
    if not value:return None
    try:return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:return None

def _current_health_rows(run_started_at,path=Path("state/source_health.json")):
    """Return only source-health rows written by this discovery invocation.

    source_health.json is cumulative. Reusing older OK rows as if they ran in the
    current cycle can incorrectly advance a tenant/provider watermark and create
    a discovery gap. Filtering by checked_at keeps scheduler decisions tied to
    work that actually happened in this run.
    """
    try:
        health=json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    floor=run_started_at-timedelta(seconds=2)
    rows=[]
    for row in health.values() if isinstance(health,dict) else []:
        if not isinstance(row,dict):continue
        checked=_parse_health_time(row.get("checked_at"))
        if checked is not None and checked>=floor:
            rows.append(row)
    return rows

def _provider_statuses(config,coverage,errors,current_health_rows):
    """Build status for every provider actually configured/executed this cycle.

    OK advances a provider watermark. PARTIAL/ERROR keep it for catch-up and are
    retryable in the current slot. DEGRADED means units were intentionally
    quarantined as unhealthy: keep the watermark but do not hammer the same
    blocked source on every recovery heartbeat.
    """
    portal_providers={
        row.get("provider") for row in config.get("discovery_portal",[])
        if isinstance(row,dict) and row.get("enabled",True) and row.get("provider")
    }
    configured_counts=dict((coverage or {}).get("configured_units_by_provider") or {})
    if configured_counts:
        configured_sources={name for name,count in configured_counts.items() if count}
    else:
        provider_names=tuple(dict.fromkeys(ALL_ATS_PROVIDERS+("career_site","dice","ziprecruiter","monster")+tuple(portal_providers)))
        configured_sources={
            name for name in provider_names
            if (config.get(name) and (not isinstance(config.get(name),dict) or config.get(name,{}).get("enabled",False)))
        }
        configured_sources.update(portal_providers)
        configured_counts={name:(len(config.get(name,[]) or []) if isinstance(config.get(name),list) else 1) for name in configured_sources}
    by_provider={}
    for row in current_health_rows:
        source=row.get("source")
        if source:by_provider.setdefault(source,[]).append(str(row.get("status") or "").upper())
    source_status={}
    for name in sorted(configured_sources):
        statuses=by_provider.get(name,[])
        provider_errors=[e for e in errors if e.get("source")==name]
        if statuses:
            has_ok="OK" in statuses
            has_error="ERROR" in statuses
            has_skipped="SKIPPED_UNHEALTHY" in statuses
            if has_error and has_ok:
                source_status[name]="PARTIAL"
            elif has_error:
                source_status[name]="ERROR"
            elif has_skipped:
                source_status[name]="DEGRADED"
            else:
                source_status[name]="OK"
            continue
        # Compatibility fallback for mocked/legacy discovery calls that do not
        # persist current health rows.
        if not provider_errors:
            source_status[name]="OK"
        else:
            failed_units={e.get("company") for e in provider_errors if e.get("company")}
            count=int(configured_counts.get(name) or 1)
            source_status[name]="PARTIAL" if failed_units and len(failed_units)<count else "ERROR"
    return source_status

def _freshness_groups(source,rows,provider_cutoff,source_unit_since):
    """Group rows by the exact cutoff that must govern final posting freshness.

    Workday tenants are independent failure domains. Discovery already scans each
    tenant with its own hours window, so finalization must retain that same tenant
    cutoff instead of inheriting the provider-wide oldest watermark.
    """
    groups={}
    unit_since=source_unit_since or {}
    for job in rows:
        cutoff=provider_cutoff
        if source=="workday":
            company=job.get("company_key") or job.get("company")
            if company:
                cutoff=unit_since.get(f"workday:{company}",provider_cutoff)
        groups.setdefault(cutoff,[]).append(job)
    return groups

def run(source_config,hours=24,only_source=None,dice_search_terms=None,ledger_path="generated/job_ledger.json",since=None,scan_now=None,source_since=None,source_hours=None,source_unit_hours=None,source_unit_since=None):
    """Discover and eligibility-filter jobs only; no JD/resume score is used."""
    profile=load_profile();ledger=load_ledger(ledger_path)
    config=load_sources(source_config)
    run_started_at=datetime.now(timezone.utc)
    discovered_result=discover(config,only_source,dice_search_terms,hours=hours,source_hours=source_hours,source_unit_hours=source_unit_hours,return_coverage=True)
    if len(discovered_result)==3:
        jobs,errors,coverage=discovered_result
    else:
        jobs,errors=discovered_result
        coverage={}
    company_registry=load_company_registry()
    learn_companies_from_jobs(jobs,company_registry);save_company_registry(company_registry)
    source_since=source_since or {}
    source_unit_since=source_unit_since or {}
    if source_since:
        jobs24=[];stale=[];already=[]
        by_source={}
        for job in jobs:by_source.setdefault(job.get("source"),[]).append(job)
        for source,rows in by_source.items():
            source_cutoff=source_since.get(source,since)
            for cutoff,group in _freshness_groups(source,rows,source_cutoff,source_unit_since).items():
                if cutoff:
                    for job in group:job["freshness_cutoff"]=cutoff
                fresh,old,seen=fresh_jobs(group,hours,since=cutoff,now=scan_now)
                jobs24.extend(fresh);stale.extend(old);already.extend(seen)
    else:
        # A unit cutoff is useful only when a provider cutoff map is also active;
        # standalone/manual runs continue to use the caller's global window.
        if since:
            for job in jobs:job["freshness_cutoff"]=since
        jobs24,stale,already=fresh_jobs(jobs,hours,since=since,now=scan_now)
    eligible=[];skipped=[];reason_counts=Counter()
    for raw in jobs24:
        processed,key,prior=seen_or_submitted(raw,ledger)
        if processed:
            skipped.append({"job":raw,"reasons":["already processed in persistent ledger"],"action":"SKIP_ALREADY_PROCESSED"});reason_counts["already_processed_ledger"]+=1;continue
        record_seen(raw,ledger,"DISCOVERED")
        eligibility=two_category_filter(raw,profile);ok,reasons=passes_hard_filters(raw,profile)
        if not ok:
            skipped.append({"job":raw,"reasons":reasons,"eligibility":eligibility,"action":"SKIP"})
            for reason in reasons:reason_counts[_reason_key(reason)]+=1
            continue
        eligible.append({"job":raw,"eligibility":eligibility,"action":"ELIGIBLE_FOR_RESUME"})
    eligible,duplicates=_dedup_eligible(eligible)
    for item in eligible:record_seen(item["job"],ledger,"ELIGIBLE_FOR_RESUME")
    save_ledger(ledger,ledger_path)

    current_health=_current_health_rows(run_started_at)
    source_status=_provider_statuses(config,coverage,errors,current_health)

    source_errors={}
    for error in errors:
        source=error.get("source")
        if source:source_errors.setdefault(source,[]).append(error)

    # Expose only unit statuses written during this invocation. Persisted health is
    # cumulative and must never make an old successful scan look current.
    source_unit_status={}
    for row in current_health:
        source=row.get("source");company=row.get("company")
        if source and company:
            source_unit_status[f"{source}:{company}"]={
                "source":source,"company":company,"status":row.get("status"),
                "jobs_returned":row.get("jobs_returned",0),"error":row.get("error"),
                "checked_at":row.get("checked_at")
            }
    # Backfill explicit adapter errors when tests/legacy callers do not persist
    # source-health, preserving backward-compatible Workday status strings.
    for error in errors:
        source=error.get("source");company=error.get("company")
        if source and company and f"{source}:{company}" not in source_unit_status:
            source_unit_status[f"{source}:{company}"]="ERROR" if source=="workday" else {
                "source":source,"company":company,"status":"ERROR","jobs_returned":0,
                "error":error.get("error"),"checked_at":None
            }

    target_fresh=sum(bool(j.get("target_company")) for j in jobs24)
    target_eligible=sum(bool((x.get("job") or {}).get("target_company")) for x in eligible)
    target_rejected=sum(bool((x.get("job") or {}).get("target_company")) for x in skipped)
    diagnostics={
        "fresh_jobs_checked":len(jobs24),"target_company_jobs":target_fresh,"target_company_eligible":target_eligible,"target_company_rejected":target_rejected,"wrong_job_family":reason_counts["wrong_job_family"],
        "location_outside_us":reason_counts["location_outside_us"],"employment_type_mismatch":reason_counts["employment_type_mismatch"],
        "experience_mismatch":reason_counts["experience_mismatch"],"no_future_sponsorship":reason_counts["no_future_sponsorship"],
        "citizenship_restriction":reason_counts["citizenship_restriction"],"clearance_restriction":reason_counts["clearance_restriction"],
        "excluded_prior_employer":reason_counts["excluded_prior_employer"],
        "duplicates_removed":len(duplicates),"outside_target_company":reason_counts["outside_target_company"],
        "other_hard_filter":reason_counts["other_hard_filter"],"already_processed_ledger":reason_counts["already_processed_ledger"],"eligible_for_resume":len(eligible),
    }
    return {
        "discovered":len(jobs),"fresh_verified_within_hours":len(jobs24),"older_or_unverified":len(stale),"already_processed":len(already),
        "eligible":len(eligible),"target_company_jobs":target_fresh,"target_company_eligible":target_eligible,"target_company_rejected":target_rejected,"filtered_out":len(skipped)+len(duplicates),"filter_reason_counts":diagnostics,
        "action_counts":{"ELIGIBLE_FOR_RESUME":len(eligible),"SKIP":len(skipped),"SKIP_DUPLICATE":len(duplicates)},"errors":errors,"source_status":source_status,"source_errors":source_errors,"source_unit_status":source_unit_status,
        "coverage":coverage,"results":eligible,"hard_filter_rejections":skipped,"duplicate_rejections":duplicates,
    }

def _print_diagnostics(d,hours):
    print(f"\nLAST {hours} HOURS — ELIGIBILITY STAGE",flush=True)
    labels=[("Fresh verified jobs","fresh_jobs_checked"),("Wrong job family","wrong_job_family"),("Location outside US","location_outside_us"),("Employment type mismatch","employment_type_mismatch"),("Experience mismatch","experience_mismatch"),("No future sponsorship","no_future_sponsorship"),("Citizenship restriction","citizenship_restriction"),("Clearance restriction","clearance_restriction"),("Excluded prior employer","excluded_prior_employer"),("Duplicates removed","duplicates_removed"),("Other eligibility filter","other_hard_filter"),("Already processed ledger","already_processed_ledger"),("Eligible for resume","eligible_for_resume")]
    for label,key in labels:print(f"{label + ':':34} {d.get(key,0)}",flush=True)

def _print_eligible(results):
    print("\nELIGIBLE JOBS FOR RESUME STAGE",flush=True)
    if not results:print("None",flush=True);return
    for i,item in enumerate(results,1):
        raw=item["job"];elig=item["eligibility"];company=raw.get("company_key") or raw.get("company") or "Unknown"
        sponsorship=elig.get("sponsorship",{}).get("category") or "SPONSORSHIP_UNKNOWN"
        print(f"{i}. [{raw.get('source','?')}] {company} | {raw.get('title','')} | {raw.get('location') or 'Provider US-scoped / location not stated'}",flush=True)
        print(f"   sponsorship: {sponsorship}",flush=True)
        if raw.get("url"):print(f"   {raw['url']}",flush=True)

def _print_rejection_samples(items,limit=20):
    print("\nELIGIBILITY REJECTION SAMPLES",flush=True)
    if not items:print("None",flush=True);return
    for i,item in enumerate(items[:limit],1):
        raw=item["job"]
        print(f"{i}. [{raw.get('source','?')}] {raw.get('company_key') or 'Unknown'} | {raw.get('title','')} | {raw.get('location') or 'Location not stated'}",flush=True)
        print(f"   reasons: {'; '.join(item.get('reasons') or [])}",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--sources",default="data/job_sources.json");p.add_argument("--hours",type=int,default=24);p.add_argument("--output",help="Optional explicit output path. By default each standalone run gets a timestamped diagnostic file.");p.add_argument("--diagnostic-limit",type=int,default=20);p.add_argument("--only-source",choices=["greenhouse","lever","ashby","smartrecruiters","workday","dice","ziprecruiter"]);p.add_argument("--dice-term",action="append");p.add_argument("--ledger",default="generated/job_ledger.json");a=p.parse_args()
    report=run(a.sources,a.hours,a.only_source,a.dice_term,a.ledger);stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");default_output=f"generated/diagnostics/{stamp}_{a.only_source or 'all'}_eligible.json";out=ROOT/(a.output or default_output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("results","hard_filter_rejections","duplicate_rejections")},indent=2));_print_diagnostics(report["filter_reason_counts"],a.hours);_print_eligible(report["results"]);_print_rejection_samples(report["hard_filter_rejections"],a.diagnostic_limit);print(f"\nSaved eligible jobs to {out}")