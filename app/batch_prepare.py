from __future__ import annotations
import argparse,json
from pathlib import Path
from types import SimpleNamespace
from dotenv import load_dotenv
from app.config import load_profile
from app.reference_resume_formatter import render_llm_resume
from app.llm_resume_writer import generate_with_llm
from app.ats_audit import ats_audit
from app.pdf_export import convert_docx_to_pdf

load_dotenv()

def prepare(report_path,output_path="generated/application_manifest.json",debug_company=None):
    """Generate one best-effort tailored resume per eligibility-approved job, then audit it."""
    report=json.loads(Path(report_path).read_text(encoding="utf-8"));profile=load_profile();manifest=[]
    for item in report.get("results",[]):
        if item.get("action") != "ELIGIBLE_FOR_RESUME":continue
        raw=item["job"];elig=item["eligibility"];company=(raw.get("company_key") or raw.get("company") or "Unknown")
        if debug_company and debug_company.lower() not in company.lower():continue
        job=SimpleNamespace(company=company,title=raw.get("title") or "",description=raw.get("description") or "",location=raw.get("location"),employment_type=raw.get("employment_type"),url=raw.get("url"))
        print(f"START {job.company} | {job.title} | eligibility-approved | single best resume pass",flush=True)
        try:
            if not job.description.strip():raise RuntimeError("Eligible job has no complete JD text; full JD retrieval/resolution is required before resume tailoring.")
            print("Generating submission-ready JD-tailored resume...",flush=True);generated=generate_with_llm(job,profile);print("OpenAI response received.",flush=True)
            if not generated:raise RuntimeError("LLM resume generation is unavailable. Check OPENAI_API_KEY and RESUME_LLM_MODEL in .env.")
            resume=render_llm_resume(job,profile,generated);print(f"DOCX generated: {resume}",flush=True)
            audit=ats_audit(job,profile,resume);audit["generation_attempts"]=1;audit["generation_source"]="openai_llm_single_pass"
            pdf_path=convert_docx_to_pdf(resume) if audit["passed"] else None
            next_action="READY_TO_APPLY" if audit["passed"] else "HOLD_ATS_REVIEW"
            print(f"DONE {job.company} | passed={audit['passed']} | attempts=1 | ATS={audit.get('internal_ats_score')} | evidence={audit.get('technology_evidence_coverage')} | human={audit.get('human_quality_score')}",flush=True)
        except Exception as exc:
            print(f"RESUME PIPELINE ERROR: {exc}",flush=True);resume=None;pdf_path=None;next_action="HOLD_RESUME_ERROR";audit={"passed":False,"generation_source":"resume_pipeline_error","error":str(exc),"generation_attempts":0}
        manifest.append({"external_id":raw.get("external_id"),"source":raw.get("source"),"company":job.company,"title":job.title,"url":job.url,"experience":elig["experience"],"sponsorship":elig["sponsorship"],"resume_path":resume,"pdf_path":pdf_path,"ats_audit":audit,"next_action":next_action,"application_status":"NOT_STARTED"})
        if debug_company:break
    out=Path(output_path);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(manifest,indent=2),encoding="utf-8");return manifest

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--report",default="generated/eligible_jobs.json");ap.add_argument("--output",default="generated/application_manifest.json");ap.add_argument("--debug-company");a=ap.parse_args();rows=prepare(a.report,a.output,a.debug_company);counts={x:sum(r["next_action"]==x for r in rows) for x in ("READY_TO_APPLY","HOLD_ATS_REVIEW","HOLD_RESUME_ERROR")};print(json.dumps({"prepared":len(rows),**counts},indent=2));print(f"Saved manifest to {a.output}")
