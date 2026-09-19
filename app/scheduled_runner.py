from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo=None
    ZoneInfoNotFoundError=Exception
from app.production_cycle import run_cycle
from app.application_autofill import run as run_applications
from app.job_ledger import load_ledger, save_ledger, record_seen

def _eastern_tz():
    """Use IANA Eastern time when available; fall back to Windows local Eastern time.

    Windows Python installations may not ship the IANA tz database. The fallback
    intentionally uses the machine's local timezone so DST remains correct when
    the Windows timezone is configured as Eastern Time.
    """
    if ZoneInfo is not None:
        try:
            return ZoneInfo("America/New_York")
        except ZoneInfoNotFoundError:
            pass
    local=datetime.now().astimezone().tzinfo
    if local is None:
        raise RuntimeError("Unable to determine local timezone. Install tzdata or configure Windows timezone to Eastern Time.")
    return local

ET=_eastern_tz()
ROOT=Path(__file__).resolve().parent.parent
STATE_PATH=ROOT/"generated"/"scheduler_state.json"
BOOTSTRAP_HOUR=7
FINAL_HOUR=18
BOOTSTRAP_WINDOW_HOURS=24
INCREMENTAL_WINDOW_HOURS=1
RUN_WEEKDAYS={0,1,2,3,4}  # Monday-Friday

def _load_state():
    if not STATE_PATH.exists(): return {}
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception: return {}

def _save_state(state):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True)
    STATE_PATH.write_text(json.dumps(state,indent=2),encoding="utf-8")

def _window_for(now,state):
    day=now.date().isoformat()
    # The first successful run of each ET calendar day is the bootstrap scan.
    # This also recovers safely if the machine missed exactly 07:00.
    if state.get("bootstrap_date") != day:
        return BOOTSTRAP_WINDOW_HOURS,"bootstrap"
    return INCREMENTAL_WINDOW_HOURS,"incremental"

def _application_ledger_status(result):
    status=result.get("status") or ""
    reason=(result.get("reason") or "").lower()
    blockers=" ".join(result.get("blockers") or []).lower()
    if status=="SUBMITTED" and result.get("submitted"):
        return "SUBMITTED"
    if any(x in blockers or x in reason for x in ("captcha","mfa","verification code","two-factor","two factor")):
        return "SECURITY_BLOCKED"
    if status in {"WAITING_FOR_HUMAN_VERIFICATION"}:
        return "SECURITY_BLOCKED"
    if any(x in reason for x in (
        "timeout","timed out","connection","network","temporarily unavailable",
        "service unavailable","502","503","504","page did not advance",
        "could not reach application form","no safe application entry",
    )):
        return "RETRY_APPLICATION"
    if status in {"INSPECTED_NO_CHANGES"}:
        return "RETRY_APPLICATION"
    return "MANUAL_ACTION_REQUIRED"

def _retry_application_items(ledger_path):
    rows=[]
    for row in (load_ledger(ledger_path).get("jobs") or {}).values():
        if row.get("application_status")!="RETRY_APPLICATION":continue
        payload=row.get("retry_application")
        if isinstance(payload,dict) and payload.get("external_id") and payload.get("resume_path"):
            rows.append(payload)
    return rows

def _merge_retry_queue(queue_path,ledger_path):
    path=ROOT/queue_path
    current=json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    existing={x.get("external_id") for x in current}
    added=0
    for item in _retry_application_items(ledger_path):
        if item.get("external_id") in existing:continue
        current.append(item);existing.add(item.get("external_id"));added+=1
    if added:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(current,indent=2),encoding="utf-8")
    return current,added

def run_scheduled(sources="data/job_sources.json",ledger="generated/job_ledger.json",generate_resumes=True,limit=None,force=False,apply_ready=False,allow_submit=False):
    now=datetime.now(ET)
    if not force and now.weekday() not in RUN_WEEKDAYS:
        return {"status":"OUTSIDE_RUN_WINDOW","local_time":now.isoformat(),"window":"Monday-Friday 07:00-18:59 America/New_York"}
    if not force and not (BOOTSTRAP_HOUR <= now.hour <= FINAL_HOUR):
        return {"status":"OUTSIDE_RUN_WINDOW","local_time":now.isoformat(),"window":"Monday-Friday 07:00-18:59 America/New_York"}
    state=_load_state()
    hours,mode=_window_for(now,state)
    summary=run_cycle(sources=sources,hours=hours,ledger=ledger,generate_resumes=generate_resumes,limit=limit)

    # Application failures are isolated per job: CAPTCHA/MFA, unknown required
    # answers, and other manual blockers are recorded and the batch continues.
    # Persist terminal outcomes in the ledger so hourly scans do not retry them.
    queue_path=summary.get("application_queue")
    if apply_ready:
        if not queue_path:
            queue_path=f"generated/cycles/{summary['cycle_id']}_application_queue.json"
            (ROOT/queue_path).parent.mkdir(parents=True,exist_ok=True)
            (ROOT/queue_path).write_text("[]",encoding="utf-8")
            summary["application_queue"]=queue_path
        merged_queue,retry_added=_merge_retry_queue(queue_path,ledger)
        summary["application_retries_queued"]=retry_added
        summary["queued_for_application"]=sum(x.get("status")=="READY_FOR_ATS_ADAPTER" for x in merged_queue)
    if apply_ready and queue_path and summary.get("queued_for_application",0):
        output=f"generated/cycles/{summary['cycle_id']}_application_results.json"
        application_results=run_applications(
            queue_path=queue_path,
            output=output,
            limit=None,
            headless=True,
            review_seconds=0,
            inspect_only=False,
            wait_for_human_seconds=0,
            allow_submit=allow_submit,
        )
        app_ledger=load_ledger(ledger)
        queue_rows=json.loads((ROOT/queue_path).read_text(encoding="utf-8"))
        for result in application_results:
            queue_item=next((x for x in queue_rows if x.get("external_id")==result.get("external_id")),{})
            job={
                "external_id":result.get("external_id"),
                "source":queue_item.get("source") or "unknown",
                "company_key":queue_item.get("company") or "",
                "title":queue_item.get("title") or "",
                "url":result.get("url") or queue_item.get("url"),
            }
            status=result.get("status") or "MANUAL_ACTION_REQUIRED"
            # Confirmed submission is terminal. Security challenges are isolated
            # without bypassing them. Transient ATS/browser failures remain retryable.
            ledger_status=_application_ledger_status(result)
            extra={
                "application_result":status,
                "application_reason":result.get("reason"),
                "application_blockers":result.get("blockers") or [],
                "application_result_path":output,
            }
            if ledger_status=="RETRY_APPLICATION":
                extra["retry_application"]=queue_item
            else:
                extra["retry_application"]=None
            record_seen(job,app_ledger,ledger_status,**extra)
        save_ledger(app_ledger,ledger)
        summary["application_stage_enabled"]=True
        summary["application_results"]=output
        summary["applications_processed"]=len(application_results)
        summary["applications_submitted"]=sum(x.get("status")=="SUBMITTED" and x.get("submitted") for x in application_results)
        summary["applications_blocked"]=sum(_application_ledger_status(x) in {"SECURITY_BLOCKED","MANUAL_ACTION_REQUIRED"} for x in application_results)
        summary["applications_retryable"]=sum(_application_ledger_status(x)=="RETRY_APPLICATION" for x in application_results)
    else:
        summary["application_stage_enabled"]=bool(apply_ready)
        summary["applications_processed"]=0

    state.update({"last_run_at":now.isoformat(),"last_mode":mode,"last_cycle_id":summary.get("cycle_id")})
    if mode=="bootstrap": state["bootstrap_date"]=now.date().isoformat()
    _save_state(state)
    summary["scheduler_mode"]=mode
    summary["scheduler_local_time"]=now.isoformat()
    summary["daily_final_cycle"]=now.hour==FINAL_HOUR
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--sources",default="data/job_sources.json")
    p.add_argument("--ledger",default="generated/job_ledger.json")
    p.add_argument("--no-resumes",action="store_true",help="Run discovery/finalization only.")
    p.add_argument("--limit",type=int)
    p.add_argument("--force",action="store_true",help="Allow a manual test outside the 07:00-18:59 ET window.")
    p.add_argument("--apply",action="store_true",help="Run the ATS application stage for READY_TO_APPLY jobs; blockers are recorded and the batch continues.")
    p.add_argument("--allow-submit",action="store_true",help="Authorize final submission when all required answers are known and ATS confirmation can be verified.")
    a=p.parse_args()
    print(json.dumps(run_scheduled(a.sources,a.ledger,not a.no_resumes,a.limit,a.force,a.apply,a.allow_submit),indent=2))
