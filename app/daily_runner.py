from __future__ import annotations
import argparse,json,re
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
    if "location" in r:return "non_us_location"
    if "full-time/w2" in r or "full-time or w2" in r or "employment type" in r:return "not_full_time_or_w2"
    if "experience requirement" in r:return "experience_mismatch"
    if "sponsorship unavailable" in r:return "no_future_sponsorship"
    if "clearance" in r or "citizenship" in r:return "work_authorization_restriction"
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

def _dedup_eligible(items):
    """Remove obvious cross-query/provider duplicates before any paid resume generation."""
    kept=[];duplicates=[];seen={}
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

def run(source_config,hours=24):
    """Discover and eligibility-filter jobs only; no JD/resume score is used."""
    profile=load_profile();jobs,errors=discover(load_sources(source_config));jobs24,stale,already=fresh_jobs(jobs,hours)
    eligible=[];skipped=[];reason_counts=Counter()
    for raw in jobs24:
        eligibility=two_category_filter(raw,profile);ok,reasons=passes_hard_filters(raw,profile)
        if not ok:
            skipped.append({"job":raw,"reasons":reasons,"eligibility":eligibility,"action":"SKIP"})
            for reason in reasons:reason_counts[_reason_key(reason)]+=1
            continue
        eligible.append({"job":raw,"eligibility":eligibility,"action":"ELIGIBLE_FOR_RESUME"})
    eligible,duplicates=_dedup_eligible(eligible)
    diagnostics={
        "fresh_jobs_checked":len(jobs24),"wrong_job_family":reason_counts["wrong_job_family"],
        "non_us_location":reason_counts["non_us_location"],"not_full_time_or_w2":reason_counts["not_full_time_or_w2"],
        "experience_mismatch":reason_counts["experience_mismatch"],"no_future_sponsorship":reason_counts["no_future_sponsorship"],
        "work_authorization_restriction":reason_counts["work_authorization_restriction"],"duplicates_removed":len(duplicates),
        "other_hard_filter":reason_counts["other_hard_filter"],"eligible_for_resume":len(eligible),
    }
    return {
        "discovered":len(jobs),"fresh_verified_within_hours":len(jobs24),"older_or_unverified":len(stale),"already_processed":len(already),
        "eligible":len(eligible),"filtered_out":len(skipped)+len(duplicates),"filter_reason_counts":diagnostics,
        "action_counts":{"ELIGIBLE_FOR_RESUME":len(eligible),"SKIP":len(skipped),"SKIP_DUPLICATE":len(duplicates)},"errors":errors,
        "results":eligible,"hard_filter_rejections":skipped,"duplicate_rejections":duplicates,
    }

def _print_diagnostics(d,hours):
    print(f"\nLAST {hours} HOURS — ELIGIBILITY STAGE",flush=True)
    labels=[("Fresh verified jobs","fresh_jobs_checked"),("Wrong job family","wrong_job_family"),("Non-US/unverified location","non_us_location"),("Not Full-Time/W2","not_full_time_or_w2"),("Experience mismatch","experience_mismatch"),("No future sponsorship","no_future_sponsorship"),("Clearance/citizenship restriction","work_authorization_restriction"),("Duplicates removed","duplicates_removed"),("Other hard filter","other_hard_filter"),("Eligible for resume","eligible_for_resume")]
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
    p=argparse.ArgumentParser();p.add_argument("--sources",default="data/job_sources.json");p.add_argument("--hours",type=int,default=24);p.add_argument("--output",default="generated/eligible_jobs.json");p.add_argument("--diagnostic-limit",type=int,default=20);a=p.parse_args()
    report=run(a.sources,a.hours);out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("results","hard_filter_rejections","duplicate_rejections")},indent=2));_print_diagnostics(report["filter_reason_counts"],a.hours);_print_eligible(report["results"]);_print_rejection_samples(report["hard_filter_rejections"],a.diagnostic_limit);print(f"\nSaved eligible jobs to {out}")
