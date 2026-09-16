from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent.parent
STATE=ROOT/"generated"/"seen_jobs.json"
STATUS=ROOT/"generated"/"job_status.json"

def _parse(v):
    if not v:return None
    try:return datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:return None

def _load(path):
    if not path.exists():return {}
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def load_seen():return _load(STATE)
def load_status():return _load(STATUS)

def save_seen(seen):
    STATE.parent.mkdir(parents=True,exist_ok=True);STATE.write_text(json.dumps(seen,indent=2),encoding="utf-8")

def fresh_jobs(jobs,hours=24):
    """Return jobs eligible for processing in this run.
    Seeing a job no longer makes it permanently processed. Only terminal
    statuses (SUBMITTED/PERMANENT_SKIP) suppress it on later hourly runs."""
    now=datetime.now(timezone.utc);cutoff=now-timedelta(hours=hours)
    seen=load_seen();status=load_status();fresh=[];stale=[];already=[]
    terminal={"SUBMITTED","PERMANENT_SKIP"}
    for job in jobs:
        key=job["external_id"];ts=_parse(job.get("updated_at"))
        if ts is not None and ts<cutoff:
            stale.append(job);continue
        state=status.get(key,{})
        if isinstance(state,str): state={"status":state}
        if state.get("status") in terminal:
            already.append(job);continue
        if key not in seen:
            seen[key]=now.isoformat()
        if ts is None:
            first=_parse(seen.get(key))
            if first is not None and first<cutoff:
                stale.append(job);continue
            job["freshness_basis"]="first_seen";job["first_seen_at"]=seen.get(key,now.isoformat())
        fresh.append(job)
    save_seen(seen);return fresh,stale,already
