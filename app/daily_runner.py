from __future__ import annotations
import argparse,json
from pathlib import Path
from types import SimpleNamespace
from app.config import load_profile
from app.discovery import discover
from app.freshness import fresh_jobs
from app.filters import passes_hard_filters
from app.eligibility import two_category_filter
from app.scoring import analyze_job
ROOT=Path(__file__).resolve().parent.parent
def load_sources(path):return json.loads(Path(path).read_text(encoding="utf-8"))
def _action(e,s,m):
    if not e["experience"]["eligible"] or e["sponsorship"]["eligible"] is False or s<m:return "SKIP"
    return "APPLY"  # Unknown sponsorship is eligible unless the posting explicitly says no sponsorship.
def run(source_config,minimum_score=65,hours=24):
    profile=load_profile();jobs,errors=discover(load_sources(source_config));jobs24,stale,already=fresh_jobs(jobs,hours)
    results=[];skipped=[];below=[]
    for raw in jobs24:
        eligibility=two_category_filter(raw,profile);ok,reasons=passes_hard_filters(raw,profile)
        if not ok:skipped.append({"job":raw,"reasons":reasons,"eligibility":eligibility,"action":"SKIP"});continue
        job=SimpleNamespace(company=raw.get("company_key") or "Unknown",title=raw.get("title") or "",description=raw.get("description") or "",location=raw.get("location"),employment_type=raw.get("employment_type"),url=raw.get("url"))
        analysis=analyze_job(job,profile);item={"job":raw,"analysis":analysis,"eligibility":eligibility,"action":_action(eligibility,analysis["score"],minimum_score)}
        (results if analysis["score"]>=minimum_score else below).append(item)
    results.sort(key=lambda x:x["analysis"]["score"],reverse=True)
    return {"discovered":len(jobs),"fresh_or_first_seen":len(jobs24),"older_than_24h":len(stale),"already_processed":len(already),"qualified":len(results),"filtered_out":len(skipped),"scored_below_threshold":len(below),"action_counts":{"APPLY":sum(x["action"]=="APPLY" for x in results),"VERIFY_SPONSORSHIP":sum(x["action"]=="VERIFY_SPONSORSHIP" for x in results),"SKIP":len(skipped)+len(below)},"errors":errors,"results":results}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--sources",default="data/job_sources.json");p.add_argument("--min-score",type=int,default=65);p.add_argument("--hours",type=int,default=24);p.add_argument("--output",default="generated/daily_jobs.json");a=p.parse_args()
    report=run(a.sources,a.min_score,a.hours);out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding="utf-8");print(json.dumps({k:v for k,v in report.items() if k!="results"},indent=2));print(f"Saved detailed results to {out}")
