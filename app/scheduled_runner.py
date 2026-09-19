from __future__ import annotations
import argparse, json
from datetime import datetime, timedelta
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
RUN_WEEKDAYS={0,1,2,3,4}  # Monday-Friday

def _load_state():
    if not STATE_PATH.exists(): return {}
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception: return {}

def _save_state(state):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True)
    STATE_PATH.write_text(json.dumps(state,indent=2),encoding="utf-8")

def _parse_checkpoint(value):
    if not value: return None
    try:
        dt=datetime.fromisoformat(value)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=ET)
        return dt.astimezone(ET)
    except (TypeError,ValueError):
        return None

def _window_for(now,state):
    """Scan from the last successful discovery checkpoint to this run.

    Normal hourly runs therefore cover one hour. Overnight runs cover 18:00 to
    07:00, and Monday 07:00 naturally covers Friday 18:00 through Monday 07:00.
    A missing checkpoint gets a conservative first-run fallback.
    """
    checkpoint=_parse_checkpoint(state.get("last_successful_discovery_at"))
    if checkpoint and checkpoint < now:
        seconds=(now-checkpoint).total_seconds()
        return max(1,int((seconds+3599)//3600)),"checkpoint",checkpoint
    if now.weekday()==0 and now.hour==BOOTSTRAP_HOUR:
        start=now-timedelta(hours=61)
        return 61,"weekend_bootstrap",start
    if now.hour==BOOTSTRAP_HOUR:
        start=now-timedelta(hours=13)
        return 13,"overnight_bootstrap",start
    start=now-timedelta(hours=1)
    return 1,"incremental_fallback",start

def run_scheduled(sources="data/job_sources.json",ledger="generated/job_ledger.json",generate_resumes=True,limit=None,force=False,apply_ready=False,allow_submit=False):
    now=datetime.now(ET)
    if not force and now.weekday() not in RUN_WEEKDAYS:
        return {"status":"OUTSIDE_RUN_WINDOW","local_time":now.isoformat(),"window":"Monday-Friday 07:00-18:59 America/New_York"}
    if not force and not (BOOTSTRAP_HOUR <= now.hour <= FINAL_HOUR):
        return {"status":"OUTSIDE_RUN_WINDOW","local_time":now.isoformat(),"window":"Monday-Friday 07:00-18:59 America/New_York"}
    state=_load_state()
    hours,mode,window_start=_window_for(now,state)
    summary=run_cycle(sources=sources,hours=hours,ledger=ledger,generate_resumes=generate_resumes,limit=limit)
    # Advance the checkpoint only after discovery/production returned successfully.
    state.update({"last_run_at":now.isoformat(),"last_successful_discovery_at":now.isoformat(),"last_mode":mode,"last_cycle_id":summary.get("cycle_id")})
    _save_state(state)

    # Application failures are isolated per job: CAPTCHA/MFA, unknown required
    # answers, and other manual blockers are recorded and the batch continues.
    # Persist terminal outcomes in the ledger so hourly scans do not retry them.
    queue_path=summary.get("application_queue")
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
        for result in application_results:
            job={
                "external_id":result.get("external_id"),
                "source":next((x.get("source") for x in json.loads((ROOT/queue_path).read_text(encoding="utf-8")) if x.get("external_id")==result.get("external_id")),"unknown"),
                "company_key":next((x.get("company") for x in json.loads((ROOT/queue_path).read_text(encoding="utf-8")) if x.get("external_id")==result.get("external_id")),""),
                "title":next((x.get("title") for x in json.loads((ROOT/queue_path).read_text(encoding="utf-8")) if x.get("external_id")==result.get("external_id")),""),
                "url":result.get("url"),
            }
            status=result.get("status") or "MANUAL_ACTION_REQUIRED"
            # Only confirmed submissions become SUBMITTED. Blockers stay terminal
            # MANUAL_ACTION_REQUIRED and are skipped by future discovery cycles.
            ledger_status="SUBMITTED" if status=="SUBMITTED" and result.get("submitted") else "MANUAL_ACTION_REQUIRED"
            record_seen(job,app_ledger,ledger_status,
                        application_result=status,
                        application_reason=result.get("reason"),
                        application_blockers=result.get("blockers") or [],
                        application_result_path=output)
        save_ledger(app_ledger,ledger)
        summary["application_stage_enabled"]=True
        summary["application_results"]=output
        summary["applications_processed"]=len(application_results)
        summary["applications_submitted"]=sum(x.get("status")=="SUBMITTED" and x.get("submitted") for x in application_results)
        summary["applications_blocked"]=sum(x.get("status")!="SUBMITTED" or not x.get("submitted") for x in application_results)
    else:
        summary["application_stage_enabled"]=bool(apply_ready)
        summary["applications_processed"]=0

    summary["scheduler_mode"]=mode
    summary["scheduler_window_start"]=window_start.isoformat()
    summary["scheduler_window_end"]=now.isoformat()
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
