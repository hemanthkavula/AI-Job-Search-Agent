from __future__ import annotations
import argparse, json
from pathlib import Path
from types import SimpleNamespace
from app.config import load_profile
from app.resume_generator import generate_resume

def prepare(report_path: str, output_path: str="generated/application_manifest.json"):
    report=json.loads(Path(report_path).read_text(encoding="utf-8"))
    profile=load_profile()
    manifest=[]
    for item in report.get("results",[]):
        if item.get("action") not in ("APPLY","VERIFY_SPONSORSHIP"):
            continue
        raw=item["job"]; analysis=item["analysis"]; eligibility=item["eligibility"]
        job=SimpleNamespace(
          company=raw.get("company_key") or raw.get("company") or "Unknown",
          title=raw.get("title") or "",description=raw.get("description") or "",
          location=raw.get("location"),employment_type=raw.get("employment_type"),url=raw.get("url"))
        resume=generate_resume(job,analysis,profile)
        manifest.append({
          "company":job.company,"title":job.title,"url":job.url,
          "score":analysis["score"],"experience":eligibility["experience"],
          "sponsorship":eligibility["sponsorship"],"resume_path":resume,
          "next_action":"READY_TO_APPLY" if item["action"]=="APPLY" else "VERIFY_SPONSORSHIP_BEFORE_SUBMIT"
        })
    out=Path(output_path); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--report",default="generated/daily_jobs.json")
    ap.add_argument("--output",default="generated/application_manifest.json")
    args=ap.parse_args()
    rows=prepare(args.report,args.output)
    ready=sum(x["next_action"]=="READY_TO_APPLY" for x in rows)
    verify=len(rows)-ready
    print(json.dumps({"prepared":len(rows),"ready_to_apply":ready,"verify_sponsorship":verify},indent=2))
    print(f"Saved manifest to {args.output}")
