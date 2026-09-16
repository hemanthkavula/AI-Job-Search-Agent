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

def run(source_config: str, minimum_score: int = 70) -> dict:
    profile=load_profile()
    jobs, errors=discover(load_sources(source_config))
    results=[]
    skipped=[]

    for raw in jobs:
        ok, filter_reasons=passes_hard_filters(raw, profile)
        if not ok:
            skipped.append({"job":raw,"reasons":filter_reasons})
            continue

        job=SimpleNamespace(
            company=raw.get("company_key") or "Unknown",
            title=raw.get("title") or "",
            description=raw.get("description") or "",
            location=raw.get("location"),
            employment_type=raw.get("employment_type"),
            url=raw.get("url"),
        )
        analysis=analyze_job(job, profile)
        if analysis["score"] >= minimum_score:
            results.append({"job":raw,"analysis":analysis})

    results.sort(key=lambda x:x["analysis"]["score"], reverse=True)
    return {
        "discovered":len(jobs),
        "qualified":len(results),
        "filtered_out":len(skipped),
        "errors":errors,
        "results":results,
    }

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--sources", default="data/job_sources.json")
    parser.add_argument("--min-score", type=int, default=70)
    parser.add_argument("--output", default="generated/daily_jobs.json")
    args=parser.parse_args()
    report=run(args.sources,args.min_score)
    out=ROOT / args.output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(f"Discovered {report['discovered']} jobs; {report['qualified']} qualified. Saved to {out}")
