from __future__ import annotations
import argparse,json,re
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]

SUPPORTED_ATS={"greenhouse","lever","ashby","workday","smartrecruiters","icims","jobvite","dice"}
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

def build(manifest_path="generated/application_manifest.json",output="generated/application_queue.json"):
    """Queue only fully validated artifacts; never guess unknown application answers."""
    rows=json.loads(Path(manifest_path).read_text(encoding="utf-8"));queue=[]
    for r in rows:
        if r.get("next_action")!="READY_TO_APPLY":continue
        validation=r.get("artifact_validation") or {}
        pdf=r.get("pdf_path")
        # Backward compatibility: manifests created before artifact_validation was
        # persisted can still be used, but only when READY_TO_APPLY has a real PDF.
        # New manifests must continue to honor an explicit failed validation.
        resolved_pdf=_artifact_path(pdf,manifest_path)
        explicit_validation="artifact_validation" in r and r.get("artifact_validation") is not None
        # Do not silently drop READY_TO_APPLY rows because a legacy manifest
        # points to a stale/moved artifact. Queue them and let autofill produce a
        # precise MANUAL_ACTION_REQUIRED diagnostic with the expected path.
        if not pdf or not resolved_pdf:continue
        if explicit_validation and not validation.get("passed"):continue
        provider=_provider(r)
        queue.append({
          "external_id":r.get("external_id"),"source":r.get("source"),"company":r.get("company"),"title":r.get("title"),
          "url":r.get("original_url") or r.get("url"),"ats_provider":provider,"application_route":r.get("application_route") or ("DICE" if provider=="dice" else "EXTERNAL_ATS"),
          "ats_score":r.get("ats_audit",{}).get("internal_ats_score"),"resume_path":resolved_pdf,
          "artifact_validation":validation,"known_answers":_known_answers(),
          "unknown_answer_policy":"MANUAL_ACTION_REQUIRED",
          "blocker_policy":"MANUAL_ACTION_REQUIRED",
          "status":"READY_FOR_ATS_ADAPTER" if provider in SUPPORTED_ATS else "MANUAL_ACTION_REQUIRED",
          "status_reason":None if provider in SUPPORTED_ATS else "Application ATS/provider could not be determined safely."
        })
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(queue,indent=2),encoding="utf-8");return queue

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--manifest",default="generated/application_manifest.json");p.add_argument("--output",default="generated/application_queue.json");a=p.parse_args();rows=build(a.manifest,a.output);print(json.dumps({"queued":len(rows),"ready_for_adapter":sum(x["status"]=="READY_FOR_ATS_ADAPTER" for x in rows),"manual_action":sum(x["status"]=="MANUAL_ACTION_REQUIRED" for x in rows),"output":a.output},indent=2))
