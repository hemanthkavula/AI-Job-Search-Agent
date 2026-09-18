from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from app.production_cycle import run_cycle

ET=ZoneInfo("America/New_York")
ROOT=Path(__file__).resolve().parent.parent
STATE_PATH=ROOT/"generated"/"scheduler_state.json"
BOOTSTRAP_HOUR=7
FINAL_HOUR=18
BOOTSTRAP_WINDOW_HOURS=24
INCREMENTAL_WINDOW_HOURS=1

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

def run_scheduled(sources="data/job_sources.json",ledger="generated/job_ledger.json",generate_resumes=True,limit=None,force=False):
    now=datetime.now(ET)
    if not force and not (BOOTSTRAP_HOUR <= now.hour <= FINAL_HOUR):
        return {"status":"OUTSIDE_RUN_WINDOW","local_time":now.isoformat(),"window":"07:00-18:59 America/New_York"}
    state=_load_state()
    hours,mode=_window_for(now,state)
    summary=run_cycle(sources=sources,hours=hours,ledger=ledger,generate_resumes=generate_resumes,limit=limit)
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
    a=p.parse_args()
    print(json.dumps(run_scheduled(a.sources,a.ledger,not a.no_resumes,a.limit,a.force),indent=2))
