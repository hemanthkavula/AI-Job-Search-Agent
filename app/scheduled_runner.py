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
from app.application_queue import _application_gate
from app.config import load_profile
from app.job_ledger import load_ledger, save_ledger, record_seen, retry_metadata, _retry_due, _lookup

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
INCREMENTAL_WINDOW_HOURS=1
RUN_WEEKDAYS={0,1,2,3,4}  # Monday-Friday

def _load_state():
    if not STATE_PATH.exists(): return {}
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception: return {}

def _save_state(state):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True)
    STATE_PATH.write_text(json.dumps(state,indent=2),encoding="utf-8")

def _parse_state_time(value):
    if not value:return None
    try:return datetime.fromisoformat(value).astimezone(ET)
    except Exception:return None

def _scheduled_cutoff(now,state):
    """Return the exact lower bound for this scan.

    Normal hourly runs start at the last successful scan. The first run of a
    weekday starts at the previous weekday's 18:00 cutoff; Monday therefore
    catches Friday 18:00 through Monday morning. If a daytime run was missed,
    the next run catches up from the last successful scan instead of losing jobs.
    """
    last=_parse_state_time(state.get("last_successful_scan_at"))
    today=now.date()
    # Construct the prior scheduled close as a local wall-clock time instead of
    # subtracting elapsed hours. This preserves 18:00 Eastern across DST changes.
    days_back=3 if now.weekday()==0 else 1
    prior_date=today-timedelta(days=days_back)
    prior_close=datetime(prior_date.year,prior_date.month,prior_date.day,FINAL_HOUR,tzinfo=ET)
    if last is None:return prior_close,"bootstrap"
    # The persisted watermark is authoritative. If the prior 18:00 run was
    # missed (for example the last success was 17:00), resume at 17:00 so no
    # posting interval is silently lost.
    if last.date()!=today:return last,"bootstrap"
    return last,"incremental"

def _window_for(now,state):
    cutoff,mode=_scheduled_cutoff(now,state)
    seconds=max(1,(now-cutoff).total_seconds())
    return seconds/3600.0,mode,cutoff

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
    # A fully autofilled application intentionally stopped at the final review
    # boundary is healthy pending work, not a blocker. Keep it replayable so a
    # later explicitly authorized run can submit the same approved payload.
    if status=="AUTOFILLED_REVIEW_REQUIRED" and not result.get("unresolved_required") and not result.get("blockers"):
        return "READY_TO_APPLY"
    return "MANUAL_ACTION_REQUIRED"

APPLICATION_REPLAY_STATUSES={"RETRY_APPLICATION","READY_TO_APPLY","IN_PROGRESS","APPLICATION_IN_PROGRESS"}
SUBMISSION_UNCERTAIN_STATUS="SUBMISSION_ATTEMPTED"

def _retry_application_items(ledger_path):
    """Recover application work that did not reach a terminal outcome.

    Replays use the persisted queue item only. Confirmed/legacy submitted rows are
    deliberately excluded so an interrupted process cannot resubmit a known
    successful application.
    """
    rows=[]
    for row in (load_ledger(ledger_path).get("jobs") or {}).values():
        if row.get("application_status") not in APPLICATION_REPLAY_STATUSES:continue
        if row.get("application_status")=="RETRY_APPLICATION" and not _retry_due(row,"application"):continue
        payload=row.get("retry_application") or row.get("queue_item")
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
    hours,mode,cutoff=_window_for(now,state)
    # Each provider resumes from its own last successful discovery. Existing
    # scheduler state migrates safely by falling back to the global cutoff.
    providers=("greenhouse","lever","ashby","smartrecruiters","workday","successfactors","icims","oracle","career_site","eightfold","dice","ziprecruiter")
    watermarks=state.get("source_watermarks") or {}
    source_cutoffs={}
    source_hours={}
    for provider in providers:
        provider_cutoff=_parse_state_time(watermarks.get(provider)) or cutoff
        source_cutoffs[provider]=provider_cutoff.isoformat()
        source_hours[provider]=max(1,(now-provider_cutoff).total_seconds())/3600.0+(5.0/60.0)
    discovery_hours=hours+(5.0/60.0)
    # Workday tenants have independent failure domains. Preserve a watermark per
    # company so healthy tenants advance even when one tenant returns 5xx.
    try:
        source_config=json.loads((ROOT/sources).read_text(encoding="utf-8"))
    except Exception:
        source_config={}
    unit_watermarks=state.get("source_unit_watermarks") or {}
    source_unit_hours={}
    for src in source_config.get("workday",[]) or []:
        unit=src.get("company") or src.get("tenant")
        if not unit:continue
        key=f"workday:{unit}"
        unit_cutoff=_parse_state_time(unit_watermarks.get(key)) or _parse_state_time(watermarks.get("workday")) or cutoff
        source_unit_hours[key]=max(1,(now-unit_cutoff).total_seconds())/3600.0+(5.0/60.0)
    summary=run_cycle(sources=sources,hours=discovery_hours,ledger=ledger,generate_resumes=generate_resumes,limit=limit,
                      since=cutoff.isoformat(),scan_now=now,source_since=source_cutoffs,source_hours=source_hours,
                      source_unit_hours=source_unit_hours)

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
        # Persist work before opening the browser. A restart can safely recover
        # pre-submit interruptions from this exact queue payload.
        queue_rows=json.loads((ROOT/queue_path).read_text(encoding="utf-8"))
        # Defense in depth: stale/manually edited/retry queues must pass the same
        # U.S.-only, Full-Time/W-2, experience, sponsorship, citizenship and
        # clearance gate again immediately before browser automation.
        profile=load_profile()
        blocked_pre_submit=[]
        safe_queue=[]
        for queue_item in queue_rows:
            if queue_item.get("status")!="READY_FOR_ATS_ADAPTER":
                safe_queue.append(queue_item);continue
            gate_ok,gate_reasons=_application_gate(queue_item,profile)
            if gate_ok:
                safe_queue.append(queue_item)
            else:
                blocked=dict(queue_item)
                blocked["status"]="MANUAL_ACTION_REQUIRED"
                blocked["status_reason"]="Pre-submit eligibility gate blocked application: "+"; ".join(gate_reasons)
                safe_queue.append(blocked)
                blocked_pre_submit.append({"external_id":queue_item.get("external_id"),"reasons":gate_reasons})
        queue_rows=safe_queue
        (ROOT/queue_path).write_text(json.dumps(queue_rows,indent=2),encoding="utf-8")
        summary["pre_submit_gate_blocked"]=len(blocked_pre_submit)
        summary["pre_submit_gate_rejections"]=blocked_pre_submit
        summary["queued_for_application"]=sum(x.get("status")=="READY_FOR_ATS_ADAPTER" for x in queue_rows)
        if not summary["queued_for_application"]:
            summary["application_stage_enabled"]=True
            summary["applications_processed"]=0
        if not summary["queued_for_application"]:
            _save_state(state)
            summary["scan_cutoff_local"]=cutoff.isoformat()
            summary["scan_window_hours"]=hours
            summary["source_watermarks"]=watermarks
            summary["source_unit_watermarks"]=unit_watermarks
            summary["scheduler_mode"]=mode
            summary["scheduler_local_time"]=now.isoformat()
            summary["daily_final_cycle"]=now.hour==FINAL_HOUR
            return summary
        app_ledger=load_ledger(ledger)
        for queue_item in queue_rows:
            if queue_item.get("status")!="READY_FOR_ATS_ADAPTER":continue
            job={"external_id":queue_item.get("external_id"),"source":queue_item.get("source") or "unknown",
                 "company_key":queue_item.get("company") or "","title":queue_item.get("title") or "","url":queue_item.get("url")}
            record_seen(job,app_ledger,"APPLICATION_IN_PROGRESS",queue_item=queue_item,retry_application=queue_item)
        save_ledger(app_ledger,ledger)
        def _before_submit(queue_item,submit_info):
            # This write happens synchronously before the irreversible browser click.
            # SUBMISSION_ATTEMPTED is terminal, so a crash cannot auto-replay it.
            durable_ledger=load_ledger(ledger)
            job={"external_id":queue_item.get("external_id"),"source":queue_item.get("source") or "unknown",
                 "company_key":queue_item.get("company") or "","title":queue_item.get("title") or "",
                 "url":submit_info.get("url") or queue_item.get("url")}
            record_seen(job,durable_ledger,SUBMISSION_UNCERTAIN_STATUS,
                        queue_item=queue_item,retry_application=None,
                        submission_attempted=True,submission_attempt=submit_info,
                        application_reason="Final submission is about to be clicked; manual confirmation required if execution is interrupted.")
            save_ledger(durable_ledger,ledger)

        application_results=run_applications(
            queue_path=queue_path,
            output=output,
            limit=None,
            headless=True,
            review_seconds=0,
            inspect_only=False,
            wait_for_human_seconds=0,
            allow_submit=allow_submit,
            before_submit=_before_submit if allow_submit else None,
        )
        app_ledger=load_ledger(ledger)
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
            # If final submission was authorized and the browser reports a
            # submission attempt without verifiable confirmation, never replay it
            # automatically. Duplicate applications are worse than a manual check.
            if allow_submit and result.get("submission_attempted") and ledger_status!="SUBMITTED":
                ledger_status=SUBMISSION_UNCERTAIN_STATUS
            extra={
                "application_result":status,
                "application_reason":result.get("reason"),
                "application_blockers":result.get("blockers") or [],
                "application_result_path":output,
            }
            if ledger_status=="RETRY_APPLICATION":
                _,existing=_lookup(job,app_ledger)
                meta=retry_metadata(existing or {},"application")
                extra.update(meta)
                if meta["application_retry_exhausted"]:
                    ledger_status="MANUAL_ACTION_REQUIRED"
                    extra["retry_application"]=None
                    extra["retry_exhausted_reason"]="Application retry limit reached"
                else:
                    extra["retry_application"]=queue_item
            else:
                extra["retry_application"]=None
            if ledger_status==SUBMISSION_UNCERTAIN_STATUS:
                extra["application_reason"]=result.get("reason") or "Submission was attempted but confirmation was not verified; manual confirmation required before any retry."
            record_seen(job,app_ledger,ledger_status,**extra)
        save_ledger(app_ledger,ledger)
        summary["application_stage_enabled"]=True
        summary["application_results"]=output
        summary["applications_processed"]=len(application_results)
        summary["applications_submitted"]=sum(x.get("status")=="SUBMITTED" and x.get("submitted") for x in application_results)
        summary["applications_ready_for_review"]=sum(_application_ledger_status(x)=="READY_TO_APPLY" for x in application_results)
        summary["applications_blocked"]=sum(_application_ledger_status(x) in {"SECURITY_BLOCKED","MANUAL_ACTION_REQUIRED"} for x in application_results)
        summary["applications_retryable"]=sum(_application_ledger_status(x)=="RETRY_APPLICATION" for x in application_results)
    else:
        summary["application_stage_enabled"]=bool(apply_ready)
        summary["applications_processed"]=0

    # Advance only providers that completed without discovery errors. A failed
    # provider keeps its old watermark and catches the missed interval next run.
    source_status=summary.get("source_status") or {}
    # Seed every provider with the cutoff actually used for this cycle. This
    # safely migrates legacy state that only has the global watermark: a failed
    # provider keeps the old cutoff instead of falling forward to the new global
    # success timestamp on the next run.
    next_watermarks={provider:source_cutoffs[provider] for provider in providers}
    next_watermarks.update(watermarks)
    for provider,status in source_status.items():
        if status=="OK":next_watermarks[provider]=now.isoformat()
    next_unit_watermarks=dict(unit_watermarks)
    unit_status=summary.get("source_unit_status") or {}
    for key,status in unit_status.items():
        if key not in next_unit_watermarks:
            next_unit_watermarks[key]=watermarks.get("workday") or source_cutoffs["workday"]
        if status=="OK":
            next_unit_watermarks[key]=now.isoformat()
    # Keep the provider-level Workday watermark as the oldest tenant watermark.
    # This remains a conservative fallback for legacy code/state while actual
    # Workday network windows use the more precise per-tenant values above.
    workday_values=[_parse_state_time(v) for k,v in next_unit_watermarks.items() if k.startswith("workday:")]
    workday_values=[v for v in workday_values if v is not None]
    if workday_values:
        next_watermarks["workday"]=min(workday_values).isoformat()
    state.update({"last_run_at":now.isoformat(),"last_successful_scan_at":now.isoformat(),"last_mode":mode,"last_cycle_id":summary.get("cycle_id"),"source_watermarks":next_watermarks,"source_unit_watermarks":next_unit_watermarks})
    summary["scan_cutoff_local"]=cutoff.isoformat()
    summary["scan_window_hours"]=hours
    _save_state(state)
    summary["source_watermarks"]=next_watermarks
    summary["source_unit_watermarks"]=next_unit_watermarks
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
