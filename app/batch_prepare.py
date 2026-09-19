from __future__ import annotations
import argparse,json,shutil
from pathlib import Path
from types import SimpleNamespace
from dotenv import load_dotenv
from app.config import load_profile
from app.reference_resume_formatter import render_llm_resume
from app.llm_resume_writer import generate_with_llm
from app.ats_audit import ats_audit
from app.pdf_export import convert_docx_to_pdf, validate_docx_pdf_parity
from app.jd_coverage_plan import build_coverage_plan

load_dotenv()

MAX_RESUME_ATTEMPTS=3
MAX_ARTIFACT_ATTEMPTS=3
MIN_COVERAGE_TARGETS=3

def _base_resume_payload(profile):
    """Build the standard resume strictly from the candidate profile; no JD tailoring or LLM."""
    return {
        "summary": " ".join(profile.get("summary_source") or []),
        "skills": profile.get("skill_categories") or {},
        "experience": [
            {"company": row.get("company"), "bullets": list(row.get("evidence") or [])}
            for row in (profile.get("experience") or [])
        ],
    }

def _discard_resume_artifact(resume_path):
    """Remove an unapproved resume and its job folder; failed candidates leave no DOCX/PDF artifacts."""
    if not resume_path:return
    try:
        p=Path(resume_path)
        parent=p.parent
        if p.exists():p.unlink()
        if parent.exists() and parent.is_dir():
            shutil.rmtree(parent,ignore_errors=True)
    except Exception:pass

def _render_base_resume(profile):
    base_job=SimpleNamespace(
        company="Base Resume",
        title=profile.get("headline") or "Senior Data Engineer",
        description="",
        location=None,
        employment_type=None,
        url=None,
    )
    return render_llm_resume(base_job,profile,_base_resume_payload(profile),output_dir="generated/base_resume")


def _audit_failure_summary(audit):
    failed=[k for k,v in audit.get("quality_gates",{}).items() if not v]
    reasons=[]
    if (audit.get("internal_ats_score") or 0)<95: reasons.append(f"ATS={audit.get('internal_ats_score')}<95")
    if (audit.get("keyword_coverage") or 0)<95: reasons.append(f"JD_coverage={audit.get('keyword_coverage')}<95")
    if audit.get("missing_jd_keywords"): reasons.append("missing="+", ".join(audit["missing_jd_keywords"]))
    if "experience_depth" in failed: reasons.append("experience_depth="+str(audit.get("experience_depth_coverage"))+"%; gaps="+", ".join(audit.get("experience_depth_gaps",[])))
    if failed: reasons.append("failed_gates="+", ".join(failed))
    if audit.get("metric_violations"): reasons.append("metric_violations="+json.dumps(audit["metric_violations"],ensure_ascii=False))
    if audit.get("unapproved_metric_claims"): reasons.append(f"unapproved_metric_claims={len(audit['unapproved_metric_claims'])}")
    return " | ".join(reasons) or "unspecified audit failure"

def _audit_feedback(audit):
    return {
        "missing_jd_keywords":audit.get("missing_jd_keywords",[]),
        "keyword_coverage":audit.get("keyword_coverage"),
        "internal_ats_score":audit.get("internal_ats_score"),
        "human_quality_score":audit.get("human_quality_score"),
        "readability_score":audit.get("readability_score"),
        "repetition_score":audit.get("repetition_score"),
        "repeated_phrases":audit.get("repeated_phrases",[]),
        "repeated_opening_verbs":audit.get("repeated_opening_verbs",{}),
        "metric_counts_by_employer":audit.get("metric_counts_by_employer",{}),
        "metric_violations":audit.get("metric_violations",{}),
        "unapproved_metric_claims":audit.get("unapproved_metric_claims",[]),
        "bullet_counts":audit.get("bullet_counts",{}),
        "bullet_count_score":audit.get("bullet_count_score"),
        "skills_taxonomy_score":audit.get("skills_taxonomy_score"),
        "quality_gates":audit.get("quality_gates",{}),
        "experience_depth_coverage":audit.get("experience_depth_coverage"),
        "experience_depth_gaps":audit.get("experience_depth_gaps",[]),
        "retry_instruction":"Correct every failed audit gate while keeping strong content from the previous version. Prioritize missing JD keywords and exact JD terminology. If experience_depth fails, move the strongest legitimate hands-on required capabilities into coherent Professional Experience bullets rather than leaving them only in Summary/Skills. Then fix structure, repetition, readability, and metric violations. The complete JD is the technical tailoring source; the master profile is not a technical-keyword whitelist. Preserve fixed factual history and do not invent certifications, employers, dates, education, numerical outcomes, or specific accomplishments."
    }

def _retryable_resume_error(exc):
    text=str(exc).lower()
    transient_markers=(
        "credit_balance_exhausted","insufficient_quota","rate limit","429",
        "temporarily unavailable","timeout","timed out","connection error",
        "connection reset","service unavailable","502","503","504"
    )
    return any(marker in text for marker in transient_markers)

def _matches(raw,company=None,title=None,external_id=None):
    if external_id and raw.get("external_id") != external_id:return False
    if company and company.lower() not in (raw.get("company_key") or raw.get("company") or "").lower():return False
    if title and title.lower() not in (raw.get("title") or "").lower():return False
    return True

def prepare(report_path,output_path="generated/application_manifest.json",debug_company=None,debug_title=None,external_id=None,limit=None):
    """Generate resumes only from FINAL_JD_VERIFIED jobs; retry only when audit fails."""
    report=json.loads(Path(report_path).read_text(encoding="utf-8"));profile=load_profile();manifest=[];matched=0
    # Spend paid resume-generation calls on the strongest application candidates first:
    # full JD + direct ATS, full JD + Dice, short usable JD + direct ATS, then short usable JD + Dice.
    priority={("FULL_JD","EXTERNAL_ATS"):0,("FULL_JD","DICE"):1,("BASE_RESUME_CONSERVATIVE","EXTERNAL_ATS"):2,("BASE_RESUME_CONSERVATIVE","DICE"):3}
    results=sorted(report.get("results",[]),key=lambda item:priority.get((item.get("job",{}).get("tailoring_mode"),item.get("job",{}).get("application_route")),9))
    for item in results:
        if item.get("action") not in ("FINAL_JD_VERIFIED",):continue
        raw=item["job"]
        if not _matches(raw,debug_company,debug_title,external_id):continue
        if limit is not None and matched>=limit:break
        matched+=1
        elig=item["eligibility"];company=(raw.get("company_key") or raw.get("company") or "Unknown")
        job=SimpleNamespace(company=company,title=raw.get("title") or "",description=raw.get("description") or "",location=raw.get("location"),employment_type=raw.get("employment_type"),url=raw.get("url"))
        print(f"START {job.company} | {job.title} | FINAL_JD_VERIFIED",flush=True)
        audit_history=[]
        try:
            if not (raw.get("description_complete") or raw.get("description_usable") or raw.get("tailoring_mode")=="BASE_RESUME_CONSERVATIVE"):raise RuntimeError("Job description is not usable for safe resume tailoring; run app.jd_finalizer before resume tailoring.")
            attempts=1
            coverage_plan=build_coverage_plan(job,profile)
            print("V1 coverage plan | targets={} | must_cover={} | preferred={}".format(coverage_plan["target_count"],coverage_plan["must_cover_terms"],coverage_plan["preferred_terms"]),flush=True)
            min_targets=1 if raw.get("tailoring_mode")=="BASE_RESUME_CONSERVATIVE" else MIN_COVERAGE_TARGETS
            if coverage_plan["target_count"] < min_targets:
                # Target extraction itself is the only reason this job would be held,
                # so fall back to the standard profile-backed base resume. This covers
                # 0 targets and low-target full JDs (for example 1-2 when minimum is 3).
                # Other resume/audit/artifact/application failures do NOT use this fallback.
                print(f"INSUFFICIENT TARGETS ({coverage_plan['target_count']}<{min_targets}) | using standard base resume; skipping JD tailoring.",flush=True)
                resume=_render_base_resume(profile)
                audit={
                    "passed":True,
                    "generation_source":"base_resume_insufficient_targets",
                    "generation_attempts":0,
                    "target_count":coverage_plan["target_count"],
                    "minimum_target_count":min_targets,
                    "internal_ats_score":None,
                    "keyword_coverage":None,
                    "experience_depth_coverage":None,
                    "recruiter_fit_score":None,
                    "human_quality_score":None,
                    "quality_gates":{},
                }
                audit_history=[{"version":"BASE","resume_path":str(resume),"audit":audit}]
                attempts=0
            else:
                print("Generating strongest submission-ready JD-tailored resume (V1)...",flush=True)
                generated=generate_with_llm(job,profile,coverage_plan=coverage_plan)
                if not generated:raise RuntimeError("LLM resume generation is unavailable. Check OPENAI_API_KEY and RESUME_LLM_MODEL in .env.")
                resume=render_llm_resume(job,profile,generated);audit=ats_audit(job,profile,resume)
                audit_history=[{"version":1,"resume_path":str(resume),"audit":audit}]
            print(f"V1 audit | passed={audit['passed']} | ATS={audit.get('internal_ats_score')} | JD_coverage={audit.get('keyword_coverage')} | experience_depth={audit.get('experience_depth_coverage')} | recruiter_fit={audit.get('recruiter_fit_score')} | human={audit.get('human_quality_score')}",flush=True)
            if not audit["passed"]: print("V1 failure | "+_audit_failure_summary(audit),flush=True)
            while not audit["passed"] and attempts<MAX_RESUME_ATTEMPTS:
                attempts+=1
                print(f"Audit failed; correcting only identified quality gaps (V{attempts}/{MAX_RESUME_ATTEMPTS})...",flush=True)
                generated=generate_with_llm(job,profile,_audit_feedback(audit),coverage_plan=coverage_plan)
                if not generated:raise RuntimeError("LLM regeneration returned no resume content")
                resume=render_llm_resume(job,profile,generated);audit=ats_audit(job,profile,resume)
                audit_history.append({"version":attempts,"resume_path":str(resume),"audit":audit})
                print(f"V{attempts} audit | passed={audit['passed']} | ATS={audit.get('internal_ats_score')} | JD_coverage={audit.get('keyword_coverage')} | experience_depth={audit.get('experience_depth_coverage')} | recruiter_fit={audit.get('recruiter_fit_score')} | human={audit.get('human_quality_score')}",flush=True)
                if not audit["passed"]: print(f"V{attempts} failure | "+_audit_failure_summary(audit),flush=True)
            audit["generation_attempts"]=attempts;audit["generation_source"]="openai_llm_quality_driven"
            pdf_path=None
            artifact_validation={"passed":False,"reason":"Resume audit did not pass","attempts":0}
            if audit["passed"]:
                # Artifact failure is a rendering problem, not a content problem.
                # Keep the approved DOCX unchanged and retry converting that SAME
                # Word file. Never spend another LLM call or rebuild a different PDF.
                # Headless conversion is deterministic for an unchanged DOCX. Convert once;
                # repeating the same render cannot repair a parity mismatch and can hide
                # environment/setup problems. Preserve the approved DOCX for later retry.
                artifact_attempt=1
                pdf_path=convert_docx_to_pdf(resume)
                artifact_validation=validate_docx_pdf_parity(resume,pdf_path)
                artifact_validation["attempts"]=artifact_attempt
                if not artifact_validation["passed"]:
                    print("PDF parity/conversion failed; holding the unchanged approved DOCX | "+json.dumps(artifact_validation,ensure_ascii=False),flush=True)
            if not audit["passed"]:
                # Tailored drafts are temporary until the quality audit passes.
                # Failed jobs must not leave resume folders or Word/PDF artifacts.
                _discard_resume_artifact(resume)
                for h in audit_history:
                    _discard_resume_artifact(h.get("resume_path"))
                    h["resume_path"]=None
                resume=None
                pdf_path=None
                next_action="HOLD_ATS_REVIEW"
            elif not artifact_validation["passed"]:
                next_action="HOLD_ARTIFACT_VALIDATION"
                print("ARTIFACT HOLD after deterministic headless conversion | "+json.dumps(artifact_validation,ensure_ascii=False),flush=True)
            else:
                next_action="READY_TO_APPLY"
            print(f"DONE {job.company} | passed={audit['passed']} | attempts={attempts} | ATS={audit.get('internal_ats_score')} | JD_coverage={audit.get('keyword_coverage')} | experience_depth={audit.get('experience_depth_coverage')} | recruiter_fit={audit.get('recruiter_fit_score')} | human={audit.get('human_quality_score')}",flush=True)
        except Exception as exc:
            # Clean up any draft that may have been rendered before a later pipeline failure.
            try:_discard_resume_artifact(locals().get("resume"))
            except Exception:pass
            for h in locals().get("audit_history",[]):
                _discard_resume_artifact(h.get("resume_path"))
                h["resume_path"]=None
            retryable=_retryable_resume_error(exc)
            print(f"RESUME PIPELINE ERROR: {exc}",flush=True);resume=None;pdf_path=None;next_action="RETRY_RESUME_GENERATION" if retryable else "HOLD_RESUME_ERROR";audit={"passed":False,"generation_source":"resume_pipeline_error","error":str(exc),"generation_attempts":0,"retryable":retryable};artifact_validation={"passed":False,"reason":str(exc)}
        manifest.append({"external_id":raw.get("external_id"),"source":raw.get("source"),"company":job.company,"title":job.title,"url":job.url,"original_url":raw.get("original_url"),"ats_provider":raw.get("ats_provider"),"ats_identifier":raw.get("ats_identifier"),"ats_resolution":raw.get("ats_resolution"),"application_route":raw.get("application_route"),"tailoring_mode":raw.get("tailoring_mode"),"description":raw.get("description"),"description_complete":raw.get("description_complete"),"description_usable":raw.get("description_usable"),"employment_type":raw.get("employment_type"),"location":raw.get("location"),"eligibility":elig,"experience":elig["experience"],"sponsorship":elig["sponsorship"],"resume_path":resume,"pdf_path":pdf_path,"ats_audit":audit,"artifact_validation":locals().get("artifact_validation",{}),"audit_history":locals().get("audit_history",[]),"next_action":next_action,"application_status":"NOT_STARTED"})
    out=Path(output_path);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(manifest,indent=2),encoding="utf-8");return manifest

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--report",default="generated/eligible_jobs.json");ap.add_argument("--output",default="generated/application_manifest.json");ap.add_argument("--debug-company");ap.add_argument("--debug-title");ap.add_argument("--external-id");ap.add_argument("--limit",type=int);a=ap.parse_args()
    rows=prepare(a.report,a.output,a.debug_company,a.debug_title,a.external_id,a.limit);counts={x:sum(r["next_action"]==x for r in rows) for x in ("READY_TO_APPLY","HOLD_ATS_REVIEW","HOLD_ARTIFACT_VALIDATION","HOLD_RESUME_ERROR")};print(json.dumps({"prepared":len(rows),**counts},indent=2));print(f"Saved manifest to {a.output}")
