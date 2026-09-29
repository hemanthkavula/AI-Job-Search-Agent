from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,stat,time
from pathlib import Path
from types import SimpleNamespace
from dotenv import load_dotenv
from app.config import load_profile
from app.reference_resume_formatter import render_llm_resume
from app.llm_resume_writer import generate_with_llm
from app.ats_audit import ats_audit
from app.pdf_export import convert_docx_to_pdf_detailed, validate_docx_pdf_parity
from app.jd_coverage_plan import build_coverage_plan

load_dotenv()

MAX_RESUME_ATTEMPTS=3
MASTER_RESUME_PATH=os.getenv("MASTER_RESUME_PATH","assets/master_resume.pdf")
MASTER_RESUME_SHA256=os.getenv("MASTER_RESUME_SHA256","ac66a58100ad363741f78baa46b0e53ec7e37f89e4bb677a32c8dd5699bb093c")

def _prepare_base_resume(raw,job):
    """Copy the canonical master PDF byte-for-byte; never regenerate BASE content."""
    source=Path(MASTER_RESUME_PATH)
    if not source.is_file():
        raise RuntimeError(f"Canonical master resume PDF is unavailable: {source}")
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash!=MASTER_RESUME_SHA256:
        raise RuntimeError(f"Canonical master resume SHA-256 mismatch: {source_hash}")
    final_root=Path(__file__).resolve().parents[1]/FINAL_RESUME_DIR
    safe_company=re.sub(r"[^A-Za-z0-9._-]+","_",job.company).strip("_") or "company"
    safe_title=re.sub(r"[^A-Za-z0-9._-]+","_",job.title).strip("_") or "role"
    final_dir=final_root/(safe_company+"_"+safe_title+"_BASE")
    final_dir.mkdir(parents=True,exist_ok=False)
    pdf=final_dir/"master_resume.pdf"
    shutil.copyfile(source,pdf)
    if source.read_bytes()!=pdf.read_bytes():
        shutil.rmtree(final_dir,ignore_errors=True)
        raise RuntimeError("Canonical master resume byte-integrity check failed")
    return str(pdf)


def _discard_resume_artifact(resume_path):
    """Remove an unapproved resume and its job folder; failed candidates leave no DOCX/PDF artifacts."""
    if not resume_path:return
    p=Path(resume_path)
    parent=p.parent
    try:
        # Generated resume folders are created by this process, so normal
        # recursive deletion is sufficient on Linux and Windows. Avoid rmtree
        # callbacks: callback signatures differ across supported Python versions
        # and can accidentally invoke os.open with the wrong arguments.
        if parent.exists() and parent.is_dir():
            shutil.rmtree(parent)
        elif p.exists():
            p.unlink()
    except Exception as exc:
        print(f"WARNING: failed to remove rejected resume artifact {p}: {exc}",flush=True)

DRAFT_RESUME_DIR="generated/.resume_drafts"
FINAL_RESUME_DIR="generated/resumes"

def _render_draft(job,profile,payload):
    """Render an audit-only DOCX outside the user-visible final resumes tree."""
    return render_llm_resume(job,profile,payload,output_dir=DRAFT_RESUME_DIR)

def _promote_approved_resume(draft_path):
    """Move only the audit-approved DOCX into generated/resumes."""
    draft=Path(draft_path)
    final_root=Path(__file__).resolve().parents[1]/FINAL_RESUME_DIR
    final_dir=final_root/draft.parent.name
    final_dir.mkdir(parents=True,exist_ok=False)
    final_path=final_dir/draft.name
    shutil.move(str(draft),str(final_path))
    # Remove the now-empty temporary attempt folder.
    try:draft.parent.rmdir()
    except OSError:pass
    return str(final_path)

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

def _audit_feedback(audit, prior_audits=None):
    prior_audits=prior_audits or []
    preserved=[]
    for prior in prior_audits:
        prior_audit=prior.get("audit",{}) if isinstance(prior,dict) else {}
        for term in prior_audit.get("experience_covered_terms",[]):
            if term not in preserved:preserved.append(term)
    return {
        "missing_jd_keywords":audit.get("missing_jd_keywords",[]),
        "previously_demonstrated_experience_terms_to_preserve":preserved,
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
        "retry_instruction":"Correct every failed audit gate without regressing gates or JD requirements that passed in any prior attempt. Preserve every term in previously_demonstrated_experience_terms_to_preserve in coherent Professional Experience bullets while fixing the current failure. Prioritize missing JD keywords and exact JD terminology. If experience_depth fails, move the strongest required capabilities into Professional Experience rather than leaving them only in Summary/Skills. If metrics fail, remove or rewrite only the unapproved metric claim while retaining previously demonstrated JD technologies and responsibilities. Then fix structure, repetition and readability without dropping prior coverage. The complete JD is the technical tailoring source; the master profile is not a technical-keyword whitelist. Preserve fixed factual history and do not invent certifications, employers, dates, education, or numerical outcomes."
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
    results=sorted(report.get("results",[]),key=lambda item:{("FULL_JD","EXTERNAL_ATS"):0,("FULL_JD","DICE"):1}.get((item.get("job",{}).get("tailoring_mode"),item.get("job",{}).get("application_route")),9))
    for item in results:
        if item.get("action") not in ("FINAL_JD_VERIFIED",):continue
        raw=item["job"]
        if not _matches(raw,debug_company,debug_title,external_id):continue
        if limit is not None and matched>=limit:break
        matched+=1
        elig=item["eligibility"];company=(raw.get("company_key") or raw.get("company") or "Unknown")
        job=SimpleNamespace(company=company,title=raw.get("title") or "",description=raw.get("description") or "",location=raw.get("location"),employment_type=raw.get("employment_type"),url=raw.get("url"))
        print(f"START {job.company} | {job.title} | FINAL_JD_VERIFIED",flush=True)
        # Reset all per-job artifact state before entering the try block. Without
        # this, Python function locals from the previous iteration can survive and
        # an early exception for the next job can delete or report the prior job's
        # approved resume.
        resume=None
        pdf_path=None
        artifact_validation={"passed":False,"reason":"Resume pipeline not completed","attempts":0}
        audit={}
        audit_history=[]
        next_action="HOLD_RESUME_ERROR"
        try:
            strategy=raw.get("resume_strategy") or {"BASE_RESUME":"BASE","LIMITED_JD":"LIMITED","FULL_JD":"FULL"}.get(raw.get("tailoring_mode"))
            if strategy=="BASE":
                attempts=0
                pdf_path=_prepare_base_resume(raw,job)
                resume=None
                audit={"passed":True,"generation_attempts":0,"generation_source":"canonical_master_resume_unchanged","resume_strategy":"BASE"}
                artifact_validation={"passed":True,"reason":"Canonical master PDF copied byte-for-byte","attempts":0,"renderer":"none","source":MASTER_RESUME_PATH,"sha256":MASTER_RESUME_SHA256}
                next_action="READY_TO_APPLY"
                print(f"DONE {job.company} | strategy=BASE | canonical master resume unchanged",flush=True)
                manifest.append({"external_id":raw.get("external_id"),"source":raw.get("source"),"company":job.company,"title":job.title,"url":job.url,"original_url":raw.get("original_url"),"requisition_id":raw.get("requisition_id") or raw.get("job_id") or raw.get("ats_job_id"),"job_id":raw.get("job_id"),"ats_job_id":raw.get("ats_job_id"),"ats_provider":raw.get("ats_provider"),"ats_identifier":raw.get("ats_identifier"),"ats_resolution":raw.get("ats_resolution"),"application_route":raw.get("application_route"),"tailoring_mode":raw.get("tailoring_mode"),"resume_strategy":"BASE","description":raw.get("description"),"description_complete":raw.get("description_complete"),"description_usable":raw.get("description_usable"),"employment_type":raw.get("employment_type"),"location":raw.get("location"),"official_location":raw.get("official_location"),"discovery_location":raw.get("discovery_location"),"location_basis":raw.get("location_basis"),"llm_job_analysis":raw.get("llm_job_analysis"),"eligibility":elig,"experience":elig["experience"],"sponsorship":elig["sponsorship"],"resume_path":None,"pdf_path":pdf_path,"ats_audit":audit,"artifact_validation":artifact_validation,"audit_history":[],"next_action":next_action,"application_status":"NOT_STARTED"})
                continue
            if strategy=="LIMITED":
                raise RuntimeError("LIMITED resume strategy requires the canonical master-resume content adapter; refusing to tailor from a partial JD alone.")
            if raw.get("description_complete") is not True or strategy!="FULL" or raw.get("tailoring_mode")!="FULL_JD":
                raise RuntimeError("FULL resume tailoring requires a complete finalized job description and FULL strategy.")
            attempts=1
            coverage_plan=build_coverage_plan(job,profile)
            print("V1 coverage plan | targets={} | must_cover={} | preferred={}".format(coverage_plan["target_count"],coverage_plan["must_cover_terms"],coverage_plan["preferred_terms"]),flush=True)
            print("Generating strongest submission-ready JD-tailored resume (V1)...",flush=True)
            generated=generate_with_llm(job,profile,coverage_plan=coverage_plan)
            if not generated:raise RuntimeError("LLM resume generation is unavailable. Check OPENAI_API_KEY and RESUME_LLM_MODEL in .env.")
            resume=_render_draft(job,profile,generated);audit=ats_audit(job,profile,resume)
            audit_history=[{"version":1,"resume_path":str(resume),"audit":audit}]
            print(f"V1 audit | passed={audit['passed']} | ATS={audit.get('internal_ats_score')} | JD_coverage={audit.get('keyword_coverage')} | experience_depth={audit.get('experience_depth_coverage')} | recruiter_fit={audit.get('recruiter_fit_score')} | human={audit.get('human_quality_score')}",flush=True)
            if not audit["passed"]: print("V1 failure | "+_audit_failure_summary(audit),flush=True)
            while not audit["passed"] and attempts<MAX_RESUME_ATTEMPTS:
                attempts+=1
                print(f"Audit failed; correcting only identified quality gaps (V{attempts}/{MAX_RESUME_ATTEMPTS})...",flush=True)
                generated=generate_with_llm(job,profile,_audit_feedback(audit,audit_history),coverage_plan=coverage_plan)
                if not generated:raise RuntimeError("LLM regeneration returned no resume content")
                # The prior failed version is no longer needed once its audit feedback
                # has been captured. Remove it before rendering the next temporary draft.
                _discard_resume_artifact(resume)
                if audit_history:audit_history[-1]["resume_path"]=None
                resume=_render_draft(job,profile,generated);audit=ats_audit(job,profile,resume)
                audit_history.append({"version":attempts,"resume_path":str(resume),"audit":audit})
                print(f"V{attempts} audit | passed={audit['passed']} | ATS={audit.get('internal_ats_score')} | JD_coverage={audit.get('keyword_coverage')} | experience_depth={audit.get('experience_depth_coverage')} | recruiter_fit={audit.get('recruiter_fit_score')} | human={audit.get('human_quality_score')}",flush=True)
                if not audit["passed"]: print(f"V{attempts} failure | "+_audit_failure_summary(audit),flush=True)
            audit["generation_attempts"]=attempts
            if attempts>0:audit["generation_source"]="openai_llm_quality_driven"
            pdf_path=None
            artifact_validation={"passed":False,"reason":"Resume audit did not pass","attempts":0}
            if audit["passed"]:
                # Nothing enters generated/resumes until content auditing is complete.
                # Promote exactly the approved DOCX, then create its PDF beside it.
                resume=_promote_approved_resume(resume)
                if audit_history:audit_history[-1]["resume_path"]=str(resume)
                # Artifact failure is a rendering problem, not a content problem.
                # Keep the approved DOCX unchanged and retry converting that SAME
                # Word file. Never spend another LLM call or rebuild a different PDF.
                # Headless conversion is deterministic for an unchanged DOCX. Convert once;
                # repeating the same render cannot repair a parity mismatch and can hide
                # environment/setup problems. Preserve the approved DOCX for later retry.
                conversion=convert_docx_to_pdf_detailed(resume,attempts=2)
                pdf_path=conversion["pdf_path"]
                artifact_validation=validate_docx_pdf_parity(resume,pdf_path)
                artifact_validation["attempts"]=conversion["attempts"]
                artifact_validation["conversion_reason"]=conversion["reason"]
                artifact_validation["renderer"]=conversion["renderer"]
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
        manifest.append({"external_id":raw.get("external_id"),"source":raw.get("source"),"company":job.company,"title":job.title,"url":job.url,"original_url":raw.get("original_url"),"requisition_id":raw.get("requisition_id") or raw.get("job_id") or raw.get("ats_job_id"),"job_id":raw.get("job_id"),"ats_job_id":raw.get("ats_job_id"),"ats_provider":raw.get("ats_provider"),"ats_identifier":raw.get("ats_identifier"),"ats_resolution":raw.get("ats_resolution"),"application_route":raw.get("application_route"),"tailoring_mode":raw.get("tailoring_mode"),"description":raw.get("description"),"description_complete":raw.get("description_complete"),"description_usable":raw.get("description_usable"),"employment_type":raw.get("employment_type"),"location":raw.get("location"),"official_location":raw.get("official_location"),"discovery_location":raw.get("discovery_location"),"location_basis":raw.get("location_basis"),"llm_job_analysis":raw.get("llm_job_analysis"),"eligibility":elig,"experience":elig["experience"],"sponsorship":elig["sponsorship"],"resume_path":resume,"pdf_path":pdf_path,"ats_audit":audit,"artifact_validation":artifact_validation,"audit_history":audit_history,"next_action":next_action,"application_status":"NOT_STARTED"})
    out=Path(output_path);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(manifest,indent=2),encoding="utf-8");return manifest

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--report",default="generated/eligible_jobs.json");ap.add_argument("--output",default="generated/application_manifest.json");ap.add_argument("--debug-company");ap.add_argument("--debug-title");ap.add_argument("--external-id");ap.add_argument("--limit",type=int);a=ap.parse_args()
    rows=prepare(a.report,a.output,a.debug_company,a.debug_title,a.external_id,a.limit);counts={x:sum(r["next_action"]==x for r in rows) for x in ("READY_TO_APPLY","HOLD_ATS_REVIEW","HOLD_ARTIFACT_VALIDATION","HOLD_RESUME_ERROR")};print(json.dumps({"prepared":len(rows),**counts},indent=2));print(f"Saved manifest to {a.output}")
