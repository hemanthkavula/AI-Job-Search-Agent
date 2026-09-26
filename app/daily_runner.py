from __future__ import annotations
import argparse,json,re
from datetime import datetime,timezone
from collections import Counter
from pathlib import Path
from app.config import load_profile
from app.discovery import discover, ALL_ATS_PROVIDERS
from app.freshness import fresh_jobs
from app.filters import passes_hard_filters
from app.eligibility import two_category_filter
from app.job_ledger import load_ledger, save_ledger, seen_or_submitted, record_seen
from app.target_companies import match_target
from app.company_registry import load as load_company_registry, save as save_company_registry, learn_from_jobs as learn_companies_from_jobs

ROOT=Path(__file__).resolve().parent.parent

def load_sources(path):return json.loads(Path(path).read_text(encoding="utf-8"))

def _reason_key(reason):
    r=(reason or "").lower()
    if "title outside" in r:return "wrong_job_family"
    if "experience requirement" in r:return "experience_mismatch"
    if "sponsorship unavailable" in r:return "no_future_sponsorship"
    return "other_hard_filter"

def _norm_company(value):
    text=re.sub(r"[^a-z0-9]+"," ",(value or "").lower()).strip()
    # Normalize common legal suffixes/duplicate provider naming.
    text=re.sub(r"\b(incorporated|inc|corp|corporation|llc|ltd|limited|company|co)\b","",text)
    return re.sub(r"\s+"," ",text).strip()

def _norm_title(value):
    text=re.sub(r"\([^)]*\)"," ",(value or "").lower())
    text=re.sub(r"\b(remote|hybrid|on[- ]site|onsite)\b"," ",text)
    text=re.sub(r"[^a-z0-9]+"," ",text)
    return re.sub(r"\s+"," ",text).strip()

SOURCE_PRIORITY={"greenhouse":0,"lever":0,"ashby":0,"smartrecruiters":0,"workday":0,"successfactors":0,"icims":0,"oracle":0,"eightfold":0,"dayforce":0,"ultipro":0,"recruiting_com":0,"adp_workforce_now":0,"workable":0,"recruitee":0,"teamtailor":0,"bamboohr":0,"phenom":0,"avature":0,"taleo":0,"cornerstone":0,"jazzhr":0,"breezyhr":0,"paylocity":0,"rippling":0,"pinpoint":0,"brassring":0,"careerplug":0,"freshteam":0,"jobscore":0,"personio":0,"career_site":1,"dice":2,"ziprecruiter":2}

def _dedup_eligible(items):
    """Prefer official ATS/company sources over aggregators for semantic duplicates."""
    kept=[];duplicates=[];seen={}
    items=sorted(items,key=lambda x: SOURCE_PRIORITY.get((x.get("job") or {}).get("source"),1))
    for item in items:
        raw=item["job"]
        company=_norm_company(raw.get("company_key") or raw.get("company"))
        title=_norm_title(raw.get("title"))
        location=re.sub(r"\s+"," ",(raw.get("location") or "").lower()).strip()
        # Company+title is the primary semantic identity. Location is used only when
        # present on both postings so multi-location openings can remain distinct.
        base=(company,title)
        candidates=seen.get(base,[])
        duplicate=None
        for prior in candidates:
            ploc=re.sub(r"\s+"," ",(prior["job"].get("location") or "").lower()).strip()
            if not location or not ploc or location==ploc:
                duplicate=prior;break
        if duplicate:
            duplicates.append({"job":raw,"duplicate_of":duplicate["job"].get("external_id"),"action":"SKIP_DUPLICATE"})
            continue
        seen.setdefault(base,[]).append(item);kept.append(item)
    return kept,duplicates

def run(source_config,hours=24,only_source=None,dice_search_terms=None,ledger_path="generated/job_ledger.json",since=None,scan_now=None,source_since=None,source_hours=None,source_unit_hours=None):
    """Discover and eligibility-filter jobs only; no JD/resume score is used.

    `hours` is the incremental posting window. Use 24 for the first daily scan and
    1 for subsequent hourly scans; the persistent ledger prevents duplicate downstream work.
    """
    profile=load_profile();ledger=load_ledger(ledger_path)
    config=load_sources(source_config)
    # Company/career-site enrichment runs separately on a slower cadence.
    # Fast job cycles only consume persisted sources and learn newly seen employers.
    jobs,errors=discover(config,only_source,dice_search_terms,hours=hours,source_hours=source_hours,source_unit_hours=source_unit_hours)
    company_registry=load_company_registry()
    learn_companies_from_jobs(jobs,company_registry);save_company_registry(company_registry)
    source_since=source_since or {}
    if source_since:
        jobs24=[];stale=[];already=[]
        by_source={}
        for job in jobs:by_source.setdefault(job.get("source"),[]).append(job)
        for source,rows in by_source.items():
            fresh,old,seen=fresh_jobs(rows,hours,since=source_since.get(source,since),now=scan_now)
            jobs24.extend(fresh);stale.extend(old);already.extend(seen)
    else:
        jobs24,stale,already=fresh_jobs(jobs,hours,since=since,now=scan_now)
    eligible=[];skipped=[];reason_counts=Counter()
    for raw in jobs24:
        # Target companies are a preferred/example employer universe, not an
        # eligibility allowlist. Jobs from any employer continue through the same
        # freshness, DE-family, US-location, Full-Time/W-2, experience,
        # sponsorship, citizenship/clearance, ledger, JD and dedup checks.
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
    # Keep production diagnostics aligned with the exact provider universe that\n    # discovery can execute, including newly learned long-tail ATS families.\n    provider_names=tuple(dict.fromkeys(ALL_ATS_PROVIDERS+("career_site","dice","ziprecruiter")))
    configured_sources={name for name in provider_names if (config.get(name) and (not isinstance(config.get(name),dict) or config.get(name,{}).get("enabled",False)))}
    failed_sources={e.get("source") for e in errors if e.get("source")}
    source_status={}
    for name in configured_sources:
        provider_errors=[e for e in errors if e.get("source")==name]
        if not provider_errors:
            source_status[name]="OK"
        elif isinstance(config.get(name),list):
            # Multi-unit providers are PARTIAL when at least one configured unit
            # remains healthy. Keep provider reporting consistent with discovery's
            # live summary (e.g. Eightfold Microsoft OK + Netflix failed).
            failed_units={e.get("company") for e in provider_errors if e.get("company")}
            configured_units={
                x.get("company") or x.get("tenant") or x.get("site") or x.get("board_token") or x.get("board_name")
                for x in config.get(name,[]) or []
            }
            configured_units.discard(None)
            source_status[name]="PARTIAL" if configured_units-failed_units else "ERROR"
        else:
            source_status[name]="ERROR"
    # Preserve provider-level failure details in the machine-readable report so
    # scheduler failures can be diagnosed without rerunning discovery manually.
    # Keep the original adapter error objects intact; they should already avoid
    # credentials/secrets and are more useful than a generic ERROR flag.
    source_errors={}
    for error in errors:
        source=error.get("source")
        if source:
            source_errors.setdefault(source,[]).append(error)
    # Workday is composed of independent company/tenant scans. Expose their
    # status separately so one broken tenant does not force every healthy tenant
    # to replay the same historical interval.
    source_unit_status={}
    failed_workday={e.get("company") for e in errors if e.get("source")=="workday"}
    for src in config.get("workday",[]) or []:
        unit=src.get("company") or src.get("tenant")
        if unit:
            source_unit_status[f"workday:{unit}"]="ERROR" if unit in failed_workday else "OK"
    target_fresh=sum(bool(j.get("target_company")) for j in jobs24)
    target_eligible=sum(bool((x.get("job") or {}).get("target_company")) for x in eligible)
    target_rejected=sum(bool((x.get("job") or {}).get("target_company")) for x in skipped)
    diagnostics={
        "fresh_jobs_checked":len(jobs24),"target_company_jobs":target_fresh,"target_company_eligible":target_eligible,"target_company_rejected":target_rejected,"wrong_job_family":reason_counts["wrong_job_family"],
        "experience_mismatch":reason_counts["experience_mismatch"],"no_future_sponsorship":reason_counts["no_future_sponsorship"],
        "duplicates_removed":len(duplicates),"outside_target_company":reason_counts["outside_target_company"],
        "other_hard_filter":reason_counts["other_hard_filter"],"already_processed_ledger":reason_counts["already_processed_ledger"],"eligible_for_resume":len(eligible),
    }
    return {
        "discovered":len(jobs),"fresh_verified_within_hours":len(jobs24),"older_or_unverified":len(stale),"already_processed":len(already),
        "eligible":len(eligible),"target_company_jobs":target_fresh,"target_company_eligible":target_eligible,"target_company_rejected":target_rejected,"filtered_out":len(skipped)+len(duplicates),"filter_reason_counts":diagnostics,
        "action_counts":{"ELIGIBLE_FOR_RESUME":len(eligible),"SKIP":len(skipped),"SKIP_DUPLICATE":len(duplicates)},"errors":errors,"source_status":source_status,"source_errors":source_errors,"source_unit_status":source_unit_status,
        "results":eligible,"hard_filter_rejections":skipped,"duplicate_rejections":duplicates,
    }

def _print_diagnostics(d,hours):
    print(f"\nLAST {hours} HOURS — ELIGIBILITY STAGE",flush=True)
    labels=[("Fresh verified jobs","fresh_jobs_checked"),("Wrong job family","wrong_job_family"),("Experience mismatch","experience_mismatch"),("No future sponsorship","no_future_sponsorship"),("Duplicates removed","duplicates_removed"),("Other eligibility filter","other_hard_filter"),("Already processed ledger","already_processed_ledger"),("Eligible for resume","eligible_for_resume")]
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
