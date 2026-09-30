from __future__ import annotations
import argparse,json,re
from datetime import datetime,timezone
from collections import Counter
from pathlib import Path
from app.config import load_profile
from app.discovery import discover, ALL_ATS_PROVIDERS
from app.discovery_health import build_source_execution_matrix, evaluate_discovery_health
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
    if "title outside" in r or "outside data-engineering job family" in r:return "wrong_job_family"
    if "experience requirement" in r:return "experience_mismatch"
    if "sponsorship unavailable" in r:return "no_future_sponsorship"
    if "citizenship" in r:return "citizenship_required"
    if "clearance" in r or "public trust" in r:return "clearance_required"
    if "outside" in r and ("united states" in r or "u.s." in r or " us " in f" {r} "):return "outside_us"
    if "employment type" in r or "full-time" in r or "w-2" in r:return "non_target_employment_type"
    if "prior employer" in r:return "excluded_prior_employer"
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
SOURCE_PRIORITY.update({"career_site":1,"dice":2,"ziprecruiter":2,"monster":2})

def _dedup_eligible(items):
    """Prefer official ATS/company sources and use the persistent identity model."""
    kept=[];duplicates=[];seen={}
    items=sorted(items,key=lambda x: SOURCE_PRIORITY.get((x.get("job") or {}).get("source"),1))
    for item in items:
        raw=item["job"];keys=identity_keys(raw);duplicate=None
        for key in keys:
            if key in seen:duplicate=seen[key];break
        if duplicate:
            duplicates.append({"job":raw,"duplicate_of":duplicate["job"].get("external_id"),"action":"SKIP_DUPLICATE"});continue
        kept.append(item)
        for key in keys:seen[key]=item
    return kept,duplicates

def _load_source_units(errors):
    source_unit_status={}
    try:
        health=json.loads(Path("state/source_health.json").read_text(encoding="utf-8"))
        # Current discovery writes a flat dict. Retain compatibility with older
        # generated health reports that wrapped rows under `sources`.
        rows=health.get("sources",[]) if isinstance(health,dict) and isinstance(health.get("sources"),list) else health.values()
        for row in rows:
            if not isinstance(row,dict):continue
            source=row.get("source") or row.get("provider");company=row.get("company")
            if source and company:
                source_unit_status[f"{source}:{company}"]={
                    "source":source,"company":company,"status":row.get("status") or row.get("effective_status"),
                    "jobs_returned":row.get("jobs_returned",0),"jobs_fetched":row.get("jobs_fetched"),
                    "error":row.get("error"),"checked_at":row.get("checked_at")
                }
    except Exception:pass
    for error in errors:
        source=error.get("source");company=error.get("company")
        if source and company and f"{source}:{company}" not in source_unit_status:
            source_unit_status[f"{source}:{company}"]={"source":source,"company":company,"status":"ERROR","jobs_returned":0,"error":error.get("error"),"checked_at":None}
    return source_unit_status

def run(source_config,hours=24,only_source=None,dice_search_terms=None,ledger_path="generated/job_ledger.json",since=None,scan_now=None,source_since=None,source_hours=None,source_unit_hours=None,healthy_baseline_discovered=None):
    """Broadly discover first, then freshness/eligibility filter downstream."""
    profile=load_profile();ledger=load_ledger(ledger_path);config=load_sources(source_config)
    discovered_result=discover(config,only_source,dice_search_terms,hours=hours,source_hours=source_hours,source_unit_hours=source_unit_hours,return_coverage=True)
    if len(discovered_result)==3:jobs,errors,coverage=discovered_result
    else:jobs,errors=discovered_result;coverage={}
    company_registry=load_company_registry();learn_companies_from_jobs(jobs,company_registry);save_company_registry(company_registry)
    source_since=source_since or {}
    if source_since:
        jobs24=[];stale=[];already=[];by_source={}
        for job in jobs:by_source.setdefault(job.get("source"),[]).append(job)
        for source,rows in by_source.items():
            fresh,old,seen=fresh_jobs(rows,hours,since=source_since.get(source,since),now=scan_now);jobs24.extend(fresh);stale.extend(old);already.extend(seen)
    else:jobs24,stale,already=fresh_jobs(jobs,hours,since=since,now=scan_now)
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

    provider_names=tuple(dict.fromkeys(ALL_ATS_PROVIDERS+("career_site","dice","ziprecruiter","monster")))
    configured_sources={name for name in provider_names if (config.get(name) and (not isinstance(config.get(name),dict) or config.get(name,{}).get("enabled",False)))}
    source_status={}
    for name in configured_sources:
        provider_errors=[e for e in errors if e.get("source")==name]
        if not provider_errors:source_status[name]="OK"
        elif isinstance(config.get(name),list):
            failed_units={e.get("company") for e in provider_errors if e.get("company")}
            configured_units={x.get("company") or x.get("tenant") or x.get("site") or x.get("board_token") or x.get("board_name") for x in config.get(name,[]) or []};configured_units.discard(None)
            source_status[name]="PARTIAL" if configured_units-failed_units else "ERROR"
        else:source_status[name]="ERROR"
    source_errors={}
    for error in errors:
        source=error.get("source")
        if source:source_errors.setdefault(source,[]).append(error)
    source_unit_status=_load_source_units(errors)

    target_fresh=sum(bool(j.get("target_company")) for j in jobs24)
    target_eligible=sum(bool((x.get("job") or {}).get("target_company")) for x in eligible)
    target_rejected=sum(bool((x.get("job") or {}).get("target_company")) for x in skipped)
    missing_date_count=sum((j.get("freshness_rejection_reason")=="missing trustworthy posting timestamp") for j in stale)
    stale_date_count=sum((j.get("freshness_rejection_reason")=="outside requested posting window") for j in stale)
    diagnostics={"fresh_jobs_checked":len(jobs24),"missing_or_unparseable_posting_date":missing_date_count,"stale_posting_date":stale_date_count,"target_company_jobs":target_fresh,"target_company_eligible":target_eligible,"target_company_rejected":target_rejected,"wrong_job_family":reason_counts["wrong_job_family"],"experience_mismatch":reason_counts["experience_mismatch"],"no_future_sponsorship":reason_counts["no_future_sponsorship"],"citizenship_required":reason_counts["citizenship_required"],"clearance_required":reason_counts["clearance_required"],"outside_us":reason_counts["outside_us"],"non_target_employment_type":reason_counts["non_target_employment_type"],"excluded_prior_employer":reason_counts["excluded_prior_employer"],"duplicates_removed":len(duplicates),"outside_target_company":reason_counts["outside_target_company"],"other_hard_filter":reason_counts["other_hard_filter"],"already_processed_ledger":reason_counts["already_processed_ledger"],"eligible_for_resume":len(eligible)}

    source_execution_matrix=build_source_execution_matrix(source_unit_status,coverage)
    discovery_health=evaluate_discovery_health(coverage=coverage,source_matrix=source_execution_matrix,discovered=len(jobs),missing_dates=missing_date_count,healthy_baseline_discovered=healthy_baseline_discovered)
    return {"technical_success":True,"discovery_health":discovery_health,"discovered":len(jobs),"fresh_verified_within_hours":len(jobs24),"older_or_unverified":len(stale),"stale_posting_date":stale_date_count,"missing_or_unparseable_posting_date":missing_date_count,"already_processed":len(already),"eligible":len(eligible),"target_company_jobs":target_fresh,"target_company_eligible":target_eligible,"target_company_rejected":target_rejected,"filtered_out":len(skipped)+len(duplicates),"filter_reason_counts":diagnostics,"action_counts":{"ELIGIBLE_FOR_RESUME":len(eligible),"SKIP":len(skipped),"SKIP_DUPLICATE":len(duplicates)},"errors":errors,"source_status":source_status,"source_errors":source_errors,"source_unit_status":source_unit_status,"source_execution_matrix":source_execution_matrix,"coverage":coverage,"results":eligible,"hard_filter_rejections":skipped,"duplicate_rejections":duplicates}

def _print_diagnostics(d,hours):
    print(f"\nLAST {hours} HOURS — ELIGIBILITY STAGE",flush=True)
    labels=[("Fresh verified jobs","fresh_jobs_checked"),("Stale posting date","stale_posting_date"),("Missing/unparseable posting date","missing_or_unparseable_posting_date"),("Wrong job family","wrong_job_family"),("Experience mismatch","experience_mismatch"),("No future sponsorship","no_future_sponsorship"),("Citizenship required","citizenship_required"),("Clearance required","clearance_required"),("Outside United States","outside_us"),("Non-target employment type","non_target_employment_type"),("Excluded prior employer","excluded_prior_employer"),("Duplicates removed","duplicates_removed"),("Other eligibility filter","other_hard_filter"),("Already processed ledger","already_processed_ledger"),("Eligible for resume","eligible_for_resume")]
    for label,key in labels:print(f"{label + ':':34} {d.get(key,0)}",flush=True)

def _print_eligible(results):
    print("\nELIGIBLE JOBS FOR RESUME STAGE",flush=True)
    if not results:print("None",flush=True);return
    for i,item in enumerate(results,1):
        raw=item["job"];elig=item["eligibility"];company=raw.get("company_key") or raw.get("company") or "Unknown";sponsorship=elig.get("sponsorship",{}).get("category") or "SPONSORSHIP_UNKNOWN"
        print(f"{i}. [{raw.get('source','?')}] {company} | {raw.get('title','')} | {raw.get('location') or 'Provider US-scoped / location not stated'}",flush=True);print(f"   sponsorship: {sponsorship}",flush=True)
        if raw.get("url"):print(f"   {raw['url']}",flush=True)

def _print_rejection_samples(items,limit=20):
    print("\nELIGIBILITY REJECTION SAMPLES",flush=True)
    if not items:print("None",flush=True);return
    for i,item in enumerate(items[:limit],1):
        raw=item["job"];print(f"{i}. [{raw.get('source','?')}] {raw.get('company_key') or 'Unknown'} | {raw.get('title','')} | {raw.get('location') or 'Location not stated'}",flush=True);print(f"   reasons: {'; '.join(item.get('reasons') or [])}",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--sources",default="data/job_sources.json");p.add_argument("--hours",type=int,default=24);p.add_argument("--output",help="Optional explicit output path. By default each standalone run gets a timestamped diagnostic file.");p.add_argument("--diagnostic-limit",type=int,default=20);p.add_argument("--only-source");p.add_argument("--dice-term",action="append");p.add_argument("--ledger",default="generated/job_ledger.json");p.add_argument("--healthy-baseline-discovered",type=int);a=p.parse_args()
    report=run(a.sources,a.hours,a.only_source,a.dice_term,a.ledger,healthy_baseline_discovered=a.healthy_baseline_discovered);stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");default_output=f"generated/diagnostics/{stamp}_{a.only_source or 'all'}_eligible.json";out=ROOT/(a.output or default_output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("results","hard_filter_rejections","duplicate_rejections")},indent=2));_print_diagnostics(report["filter_reason_counts"],a.hours);_print_eligible(report["results"]);_print_rejection_samples(report["hard_filter_rejections"],a.diagnostic_limit);print(f"\nSaved eligible jobs to {out}")
