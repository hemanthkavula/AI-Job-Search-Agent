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

def run_scheduled(sources="data/job_sources.json",ledger="generated/job_ledger.json",generate_resumes=True,limit=None,force=False):
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

    # Resume generation and the application queue are the terminal automation boundary.
    # Applications are intentionally submitted manually by the user.
    summary["application_stage_enabled"]=False
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
    a=p.parse_args()
    print(json.dumps(run_scheduled(a.sources,a.ledger,not a.no_resumes,a.limit,a.force),indent=2))
