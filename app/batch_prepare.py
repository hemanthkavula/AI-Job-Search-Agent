from __future__ import annotations
import argparse,json
from pathlib import Path
from types import SimpleNamespace
from dotenv import load_dotenv
from app.config import load_profile
from app.resume_generator import render_llm_resume
from app.llm_resume_writer import generate_with_llm
from app.ats_audit import ats_audit
from app.pdf_export import convert_docx_to_pdf

load_dotenv()

def _audit_feedback(audit):
    return {"missing_jd_keywords":audit.get("missing_jd_keywords",[]),"keyword_coverage":audit.get("keyword_coverage"),"internal_ats_score":audit.get("internal_ats_score"),"technology_evidence_coverage":audit.get("technology_evidence_coverage"),"skills_without_experience_evidence":audit.get("skills_without_experience_evidence",[]),"human_quality_score":audit.get("human_quality_score"),"readability_score":audit.get("readability_score"),"repetition_score":audit.get("repetition_score"),"repeated_phrases":audit.get("repeated_phrases",[]),"repeated_opening_verbs":audit.get("repeated_opening_verbs",{}),"metric_counts_by_employer":audit.get("metric_counts_by_employer",{}),"metric_violations":audit.get("metric_violations",{}),"bullet_counts":audit.get("bullet_counts",{}),"bullet_count_score":audit.get("bullet_count_score"),"skills_taxonomy_score":audit.get("skills_taxonomy_score"),"quality_gates":audit.get("quality_gates",{})}

def prepare(report_path,output_path="generated/application_manifest.json",min_score=80,debug_company=None,single_attempt=False):
    report=json.loads(Path(report_path).read_text(encoding="utf-8"));profile=load_profile();manifest=[]
    for item in report.get("results",[]):
        if item.get("action") not in ("APPLY","VERIFY_SPONSORSHIP"):continue
        raw=item["job"];analysis=item["analysis"];elig=item["eligibility"];score=int(analysis.get("score") or 0);company=(raw.get("company_key") or raw.get("company") or "Unknown")
        if score<min_score:print(f"SKIP {company} - score {score} < {min_score}",flush=True);continue
        if debug_company and debug_company.lower() not in company.lower():continue
        job=SimpleNamespace(company=company,title=raw.get("title") or "",description=raw.get("description") or "",location=raw.get("location"),employment_type=raw.get("employment_type"),url=raw.get("url"),discovery_score=score)
        print(f"START {job.company} | {job.title} | score={score}",flush=True)
        try:
            print("Calling OpenAI resume writer...",flush=True);generated=generate_with_llm(job,profile);print("OpenAI response received.",flush=True)
            if not generated:raise RuntimeError("LLM resume generation is unavailable. Check OPENAI_API_KEY and RESUME_LLM_MODEL in .env.")
            resume=render_llm_resume(job,profile,generated);print(f"DOCX generated: {resume}",flush=True);audit=ats_audit(job,profile,resume);attempts=1;max_attempts=1 if single_attempt else 5
            while not audit["passed"] and attempts<max_attempts:
                print(f"Quality gate failed: ATS={audit.get('internal_ats_score')} evidence={audit.get('technology_evidence_coverage')} human={audit.get('human_quality_score')}; regeneration {attempts+1}/{max_attempts}...",flush=True)
                generated=generate_with_llm(job,profile,_audit_feedback(audit))
                if not generated:raise RuntimeError("LLM regeneration returned no resume content")
                resume=render_llm_resume(job,profile,generated);audit=ats_audit(job,profile,resume);attempts+=1
            audit["generation_attempts"]=attempts;audit["generation_source"]="openai_llm";pdf_path=convert_docx_to_pdf(resume) if audit["passed"] else None;next_action="HOLD_ATS_REVIEW"
            if audit["passed"]:next_action="READY_TO_APPLY" if item["action"]=="APPLY" else "VERIFY_SPONSORSHIP_BEFORE_SUBMIT"
            print(f"DONE {job.company} | passed={audit['passed']} | attempts={attempts} | ATS={audit.get('internal_ats_score')} | evidence={audit.get('technology_evidence_coverage')} | human={audit.get('human_quality_score')}",flush=True)
        except Exception as exc:
            print(f"LLM ERROR: {exc}",flush=True);resume=None;pdf_path=None;next_action="HOLD_LLM_ERROR";audit={"passed":False,"generation_source":"llm_error","error":str(exc),"generation_attempts":0}
        manifest.append({"external_id":raw.get("external_id"),"source":raw.get("source"),"company":job.company,"title":job.title,"url":job.url,"score":score,"experience":elig["experience"],"sponsorship":elig["sponsorship"],"resume_path":resume,"pdf_path":pdf_path,"ats_audit":audit,"next_action":next_action,"application_status":"NOT_STARTED"})
        if debug_company:break
    out=Path(output_path);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(manifest,indent=2),encoding="utf-8");return manifest

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--report",default="generated/daily_jobs.json");ap.add_argument("--output",default="generated/application_manifest.json");ap.add_argument("--min-score",type=int,default=80);ap.add_argument("--debug-company");ap.add_argument("--single-attempt",action="store_true");a=ap.parse_args();rows=prepare(a.report,a.output,a.min_score,a.debug_company,a.single_attempt);counts={x:sum(r["next_action"]==x for r in rows) for x in ("READY_TO_APPLY","VERIFY_SPONSORSHIP_BEFORE_SUBMIT","HOLD_ATS_REVIEW","HOLD_LLM_ERROR")};print(json.dumps({"prepared":len(rows),**counts},indent=2));print(f"Saved manifest to {a.output}")
