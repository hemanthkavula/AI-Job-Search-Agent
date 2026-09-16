from __future__ import annotations
import argparse, json
from pathlib import Path
from types import SimpleNamespace
from app.config import load_profile
from app.discovery import discover
from app.filters import passes_hard_filters
from app.scoring import analyze_job

ROOT=Path(__file__).resolve().parent.parent

def load_sources(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def run(source_config: str, minimum_score: int = 65) -> dict:
    profile=load_profile()
    jobs,errors=discover(load_sources(source_config))
    results=[]; skipped=[]; scored_below=[]

    for raw in jobs:
        ok,filter_reasons=passes_hard_filters(raw,profile)
        if not ok:
            skipped.append({"job":raw,"reasons":filter_reasons}); continue
        job=SimpleNamespace(
            company=raw.get("company_key") or "Unknown", title=raw.get("title") or "",
            description=raw.get("description") or "", location=raw.get("location"),
            employment_type=raw.get("employment_type"), url=raw.get("url"))
        analysis=analyze_job(job,profile)
        item={"job":raw,"analysis":analysis}
        if analysis["score"]>=minimum_score: results.append(item)
        else: scored_below.append(item)

    results.sort(key=lambda x:x["analysis"]["score"],reverse=True)
    scored_below.sort(key=lambda x:x["analysis"]["score"],reverse=True)
    return {
      "discovered":len(jobs),"passed_hard_filters":len(jobs)-len(skipped),
      "qualified":len(results),"filtered_out":len(skipped),
      "scored_below_threshold":len(scored_below),"errors":errors,
      "results":results,"top_below_threshold":scored_below[:10]
    }

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--sources",default="data/job_sources.json")
    parser.add_argument("--min-score",type=int,default=65)
    parser.add_argument("--output",default="generated/daily_jobs.json")
    args=parser.parse_args()
    report=run(args.sources,args.min_score)
    out=ROOT/args.output; out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("results","top_below_threshold")},indent=2))
    print(f"Saved detailed results to {out}")
