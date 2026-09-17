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
    """Return only jobs with trustworthy posting timestamps inside the requested window.

    Strict mode intentionally does NOT treat first-seen time as proof that a job was
    posted recently. Jobs without a parseable ATS/job-board posting timestamp are
    excluded from automatic processing because the user requires postings from the
    last 24 hours only.
    """
    now=datetime.now(timezone.utc);cutoff=now-timedelta(hours=hours)
    seen=load_seen();status=load_status();fresh=[];stale=[];already=[]
    terminal={"SUBMITTED","PERMANENT_SKIP"}
    for job in jobs:
        key=job["external_id"]
        if key not in seen:seen[key]=now.isoformat()
        state=status.get(key,{})
        if isinstance(state,str):state={"status":state}
        if state.get("status") in terminal:
            already.append(job);continue
        ts=_parse(job.get("updated_at"))
        if ts is None:
            item=dict(job);item["freshness_rejection_reason"]="missing trustworthy posting timestamp"
            stale.append(item);continue
        if ts<cutoff or ts>now+timedelta(minutes=10):
            item=dict(job);item["freshness_rejection_reason"]="outside requested posting window"
            stale.append(item);continue
        job["freshness_basis"]="source_timestamp"
        fresh.append(job)
    save_seen(seen);return fresh,stale,already
