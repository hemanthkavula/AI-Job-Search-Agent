from __future__ import annotations
import argparse,json
from collections import Counter
from pathlib import Path
from app.config import load_profile
from app.discovery import discover
from app.freshness import fresh_jobs
from app.filters import passes_hard_filters
from app.eligibility import two_category_filter

ROOT=Path(__file__).resolve().parent.parent

def load_sources(path):return json.loads(Path(path).read_text(encoding="utf-8"))

def _reason_key(reason):
    r=(reason or "").lower()
    if "title outside" in r:return "wrong_job_family"
    if "non-us location" in r:return "non_us_location"
    if "full-time/w2" in r or "full-time or w2" in r or "employment type" in r:return "not_full_time_or_w2"
    if "experience requirement" in r:return "experience_mismatch"
    if "sponsorship unavailable" in r:return "no_future_sponsorship"
    return "other_hard_filter"

def run(source_config,hours=24):
    """Discover and eligibility-filter jobs only.

    Stage 1 deliberately does NOT calculate JD/resume match scores. A posting moves
    forward when it is a fresh US Data Engineering role, Full-Time/W2, compatible
    with the candidate's experience, and does not explicitly prohibit required
    future sponsorship. Unknown/not-mentioned sponsorship is allowed.
    """
    profile=load_profile();jobs,errors=discover(load_sources(source_config));jobs24,stale,already=fresh_jobs(jobs,hours)
    eligible=[];skipped=[];reason_counts=Counter()
    for raw in jobs24:
        eligibility=two_category_filter(raw,profile);ok,reasons=passes_hard_filters(raw,profile)
        if not ok:
            skipped.append({"job":raw,"reasons":reasons,"eligibility":eligibility,"action":"SKIP"})
            for reason in reasons:reason_counts[_reason_key(reason)]+=1
            continue
        eligible.append({"job":raw,"eligibility":eligibility,"action":"ELIGIBLE_FOR_RESUME"})
    diagnostics={
        "fresh_jobs_checked":len(jobs24),
        "wrong_job_family":reason_counts["wrong_job_family"],
        "non_us_location":reason_counts["non_us_location"],
        "not_full_time_or_w2":reason_counts["not_full_time_or_w2"],
        "experience_mismatch":reason_counts["experience_mismatch"],
        "no_future_sponsorship":reason_counts["no_future_sponsorship"],
        "other_hard_filter":reason_counts["other_hard_filter"],
        "eligible_for_resume":len(eligible),
    }
    return {
        "discovered":len(jobs),"fresh_verified_within_hours":len(jobs24),"older_or_unverified":len(stale),"already_processed":len(already),
        "eligible":len(eligible),"filtered_out":len(skipped),"filter_reason_counts":diagnostics,
        "action_counts":{"ELIGIBLE_FOR_RESUME":len(eligible),"SKIP":len(skipped)},"errors":errors,
        "results":eligible,"hard_filter_rejections":skipped,
    }

def _print_diagnostics(d,hours):
    print(f"\nLAST {hours} HOURS — ELIGIBILITY STAGE",flush=True)
    labels=[
        ("Fresh verified jobs","fresh_jobs_checked"),("Wrong job family","wrong_job_family"),("Non-US","non_us_location"),
        ("Not Full-Time/W2","not_full_time_or_w2"),("Experience mismatch","experience_mismatch"),
        ("No future sponsorship","no_future_sponsorship"),("Other hard filter","other_hard_filter"),
        ("Eligible for resume","eligible_for_resume"),
    ]
    for label,key in labels:print(f"{label + ':':28} {d.get(key,0)}",flush=True)

def _print_eligible(results):
    print("\nELIGIBLE JOBS FOR RESUME STAGE",flush=True)
    if not results:
        print("None",flush=True);return
    for i,item in enumerate(results,1):
        raw=item["job"];elig=item["eligibility"]
        company=raw.get("company_key") or raw.get("company") or "Unknown"
        sponsorship=elig.get("sponsorship",{}).get("status") or elig.get("sponsorship",{}).get("reason") or "unknown/not mentioned"
        print(f"{i}. [{raw.get('source','?')}] {company} | {raw.get('title','')} | {raw.get('location') or 'Location not stated'}",flush=True)
        print(f"   sponsorship: {sponsorship}",flush=True)
        if raw.get("url"):print(f"   {raw['url']}",flush=True)

def _print_rejection_samples(items,limit=20):
    print("\nELIGIBILITY REJECTION SAMPLES",flush=True)
    if not items:
        print("None",flush=True);return
    for i,item in enumerate(items[:limit],1):
        raw=item["job"]
        print(f"{i}. [{raw.get('source','?')}] {raw.get('company_key') or 'Unknown'} | {raw.get('title','')} | {raw.get('location') or 'Location not stated'}",flush=True)
        print(f"   reasons: {'; '.join(item.get('reasons') or [])}",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--sources",default="data/job_sources.json");p.add_argument("--hours",type=int,default=24);p.add_argument("--output",default="generated/eligible_jobs.json");p.add_argument("--diagnostic-limit",type=int,default=20);a=p.parse_args()
    report=run(a.sources,a.hours);out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("results","hard_filter_rejections")},indent=2));_print_diagnostics(report["filter_reason_counts"],a.hours);_print_eligible(report["results"]);_print_rejection_samples(report["hard_filter_rejections"],a.diagnostic_limit);print(f"\nSaved eligible jobs to {out}")
