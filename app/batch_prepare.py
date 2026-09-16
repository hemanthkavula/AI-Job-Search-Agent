from __future__ import annotations
import argparse,json
from pathlib import Path
from types import SimpleNamespace
from app.config import load_profile
from app.resume_generator import generate_resume, render_llm_resume
from app.llm_resume_writer import generate_with_llm
from app.ats_audit import ats_audit
from app.pdf_export import convert_docx_to_pdf
def prepare(report_path,output_path="generated/application_manifest.json"):
    report=json.loads(Path(report_path).read_text(encoding="utf-8"));profile=load_profile();manifest=[]
    for item in report.get("results",[]):
        if item.get("action") not in ("APPLY","VERIFY_SPONSORSHIP"):continue
        raw=item["job"];analysis=item["analysis"];elig=item["eligibility"]
        job=SimpleNamespace(company=raw.get("company_key") or raw.get("company") or "Unknown",title=raw.get("title") or "",description=raw.get("description") or "",location=raw.get("location"),employment_type=raw.get("employment_type"),url=raw.get("url"),discovery_score=analysis.get("score"))
        generated=generate_with_llm(job,profile)
        resume=render_llm_resume(job,profile,generated) if generated else generate_resume(job,analysis,profile)
        audit=ats_audit(job,profile,resume)
        # Quality gate: never release a sub-95 resume. Regenerate several times,
        # carrying audit feedback into analysis so the generator can prioritize
        # missing supported terminology and weak coverage on subsequent attempts.
        attempts=1
        max_attempts=5
        while not audit["passed"] and attempts < max_attempts:
            analysis=dict(analysis)
            analysis["resume_audit_feedback"]={
                "missing_supported_keywords":audit.get("missing_supported_keywords",[]),
                "keyword_coverage":audit.get("keyword_coverage"),
                "internal_ats_score":audit.get("internal_ats_score"),
                "bullet_count_score":audit.get("bullet_count_score"),
                "skills_taxonomy_score":audit.get("skills_taxonomy_score")
            }
            generated=generate_with_llm(job,profile,analysis["resume_audit_feedback"])
            resume=render_llm_resume(job,profile,generated) if generated else generate_resume(job,analysis,profile)
            audit=ats_audit(job,profile,resume)
            attempts += 1
        audit["generation_attempts"]=attempts
        pdf_path=convert_docx_to_pdf(resume) if audit["passed"] else None
        next_action="HOLD_ATS_REVIEW"
        if audit["passed"]:next_action="READY_TO_APPLY" if item["action"]=="APPLY" else "VERIFY_SPONSORSHIP_BEFORE_SUBMIT"
        manifest.append({"external_id":raw.get("external_id"),"source":raw.get("source"),"company":job.company,"title":job.title,"url":job.url,"score":analysis["score"],"experience":elig["experience"],"sponsorship":elig["sponsorship"],"resume_path":resume,"pdf_path":pdf_path,"ats_audit":audit,"next_action":next_action,"application_status":"NOT_STARTED"})
    out=Path(output_path);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(manifest,indent=2),encoding="utf-8");return manifest
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--report",default="generated/daily_jobs.json");ap.add_argument("--output",default="generated/application_manifest.json");a=ap.parse_args();rows=prepare(a.report,a.output)
    counts={x:sum(r["next_action"]==x for r in rows) for x in ("READY_TO_APPLY","VERIFY_SPONSORSHIP_BEFORE_SUBMIT","HOLD_ATS_REVIEW")}
    print(json.dumps({"prepared":len(rows),**counts},indent=2));print(f"Saved manifest to {a.output}")
