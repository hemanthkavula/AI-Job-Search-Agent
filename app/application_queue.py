from __future__ import annotations
import argparse,json,re
from pathlib import Path
from urllib.parse import urlparse
from app.config import load_profile
from app.filters import passes_hard_filters
from app.job_identity import identity_keys
from app.job_ledger import load_ledger, _lookup
from app.llm_job_analyzer import semantic_rejection_reasons

ROOT=Path(__file__).resolve().parents[1]

MANUAL_BLOCKERS=("captcha","recaptcha","hcaptcha","mfa","two-factor","2fa","verification code")

def _provider(row):
    explicit=(row.get("ats_provider") or "").lower().strip()
    if explicit:return explicit
    if (row.get("application_route") or "").upper()=="DICE":return "dice"
    host=urlparse(row.get("original_url") or row.get("url") or "").netloc.lower()
    hints={"greenhouse":"greenhouse","lever":"lever","ashby":"ashby","myworkdayjobs":"workday",
           "smartrecruiters":"smartrecruiters","icims":"icims","jobvite":"jobvite"}
    return next((p for token,p in hints.items() if token in host),"unknown")

def _known_answers():
    return {
      "authorized_to_work_us":"Yes",
      "requires_sponsorship_now":"No",
      "requires_future_sponsorship":"Yes",
      "sponsorship_statement":"I am currently authorized to work in the United States under F-1 OPT and do not require sponsorship at this time. I will require H-1B sponsorship in the future to continue working in the United States."
    }

def _artifact_path(value,manifest_path):
    if not value:return None
    raw=str(value).strip()
    # Handle Windows absolute paths even when code is inspected/run under a
    # different path flavor. On Windows, Path handles these natively; this
    # branch also preserves drive-letter paths exactly.
    if re.match(r"^[A-Za-z]:[\\/]", raw):
        return str(Path(raw))
    p=Path(raw)
    if p.is_absolute():return str(p)
    candidates=[ROOT/p,Path(manifest_path).resolve().parent/p,p.resolve()]
    for candidate in candidates:
        if candidate.exists():return str(candidate.resolve())
    # Preserve a deterministic project-root path so downstream diagnostics explain
    # exactly which artifact was expected even if it was later moved/deleted.
    return str((ROOT/p).resolve())

def _application_gate(row,profile):
    """Re-run governing eligibility immediately before a job can enter the ATS queue."""
    job={
      "external_id":row.get("external_id"),"source":row.get("source"),"company_key":row.get("company"),"title":row.get("title"),
      "location":row.get("location"),"employment_type":row.get("employment_type"),"description":row.get("description") or ""
    }
    return passes_hard_filters(job,profile)

def _queue_identity_keys(row):
    """Shared cross-source aliases used to block duplicate final submissions."""
    job=dict(row)
    # Manifest rows use company while the shared identity helper accepts either
    # company or company_key. Preserve all requisition/URL aliases when present.
    return identity_keys(job)

def build(manifest_path="generated/application_manifest.json",output="generated/application_queue.json",ledger_path="generated/job_ledger.json"):
    """Queue only fully validated, still-eligible artifacts; never trust an earlier gate alone."""
    rows=json.loads(Path(manifest_path).read_text(encoding="utf-8"));queue=[];profile=load_profile();seen_keys=set();ledger=load_ledger(ledger_path)
    submission_terminal={"SUBMITTED","SUBMITTED_CONFIRMED","SUBMISSION_ATTEMPTED","MANUAL_ACTION_REQUIRED","SECURITY_BLOCKED","PERMANENT_SKIP"}
    for r in rows:
        if r.get("next_action")!="READY_TO_APPLY":continue
        keys=_queue_identity_keys(r)
        if any(key in seen_keys for key in keys):continue
        # A stale/recovered READY_TO_APPLY manifest must never replay a job whose
        # persistent identity already reached a submission/manual/security terminal state.
        _,ledger_row=_lookup(r,ledger)
        if ledger_row and ledger_row.get("application_status") in submission_terminal:continue
        validation=r.get("artifact_validation") or {}
        pdf=r.get("pdf_path")
        # Backward compatibility: manifests created before artifact_validation was
        # persisted can still be used, but only when READY_TO_APPLY has a real PDF.
        # New manifests must continue to honor an explicit failed validation.
        resolved_pdf=_artifact_path(pdf,manifest_path)
        # Production readiness is fail-closed: legacy/stale manifests do not bypass
        # artifact validation, and the validated PDF must still exist at queue time.
        if not pdf or not resolved_pdf:continue
        if validation.get("passed") is not True:continue
        if not Path(resolved_pdf).is_file() or Path(resolved_pdf).suffix.lower()!=".pdf":continue
        provider=_provider(r)
        # Recovered/stale manifests must satisfy the same explicit employment proof
        # required by finalization; unknown metadata cannot become application-ready.
        employment_text=(str(r.get("employment_type") or "")+" "+str(r.get("description") or "")).lower()
        if not re.search(r"\b(?:full[- ]?time|permanent(?:\s+(?:employee|position))?|regular\s+employee|w-?2)\b",employment_text,re.I):
            continue
        gate_ok,gate_reasons=_application_gate(r,profile)
        if not gate_ok:
            continue
        # Re-evaluate persisted semantic evidence at the final queue boundary.
        # This prevents a recovered/stale manifest from bypassing a restriction
        # that the official-JD OpenAI verifier already established.
        semantic_reasons=semantic_rejection_reasons(r.get("llm_job_analysis"),profile)
        if semantic_reasons:
            continue
        # A direct official ATS job may retain its original discovery location when
        # the official page exposes no structured location. But whenever finalization
        # extracted an official location, require the manifest value to be exactly
        # that authoritative value before application queueing.
        official_location=(r.get("official_location") or "").strip()
        if official_location and (r.get("location") or "").strip()!=official_location:
            continue
        seen_keys.update(keys)
        queue.append({
          "external_id":r.get("external_id"),"source":r.get("source"),"company":r.get("company"),"title":r.get("title"),"requisition_id":r.get("requisition_id") or r.get("job_id") or r.get("ats_job_id"),
          "url":r.get("original_url") or r.get("url"),"ats_provider":provider,"application_route":r.get("application_route") or ("DICE" if provider=="dice" else "EXTERNAL_ATS"),
          "ats_score":r.get("ats_audit",{}).get("internal_ats_score"),"resume_path":resolved_pdf,
          "artifact_validation":validation,"known_answers":_known_answers(),
          "location":r.get("location"),"official_location":r.get("official_location"),"location_basis":r.get("location_basis"),"employment_type":r.get("employment_type"),"description":r.get("description"),"llm_job_analysis":r.get("llm_job_analysis"),
          "application_gate":{"passed":True,"reasons":[]},
          "unknown_answer_policy":"MANUAL_ACTION_REQUIRED",
          "blocker_policy":"MANUAL_ACTION_REQUIRED",
          "status":"READY_FOR_ATS_ADAPTER",
          "status_reason":None
        })
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(queue,indent=2),encoding="utf-8");return queue

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--manifest",default="generated/application_manifest.json");p.add_argument("--output",default="generated/application_queue.json");a=p.parse_args();rows=build(a.manifest,a.output);print(json.dumps({"queued":len(rows),"ready_for_adapter":sum(x["status"]=="READY_FOR_ATS_ADAPTER" for x in rows),"manual_action":sum(x["status"]=="MANUAL_ACTION_REQUIRED" for x in rows),"output":a.output},indent=2))
