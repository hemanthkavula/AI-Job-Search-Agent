from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent.parent
STATE=ROOT/"generated"/"seen_jobs.json"
def _parse(v):
    if not v:return None
    try:return datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:return None
def load_seen():
    if not STATE.exists():return {}
    try:return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:return {}
def save_seen(seen):
    STATE.parent.mkdir(parents=True,exist_ok=True);STATE.write_text(json.dumps(seen,indent=2),encoding="utf-8")
def fresh_jobs(jobs,hours=24):
    now=datetime.now(timezone.utc);cutoff=now-timedelta(hours=hours);seen=load_seen();fresh=[];stale=[];already=[]
    for job in jobs:
        key=job["external_id"];ts=_parse(job.get("updated_at"))
        if ts is not None and ts<cutoff:stale.append(job);continue
        if key in seen:already.append(job);continue
        if ts is None:
            job["freshness_basis"]="first_seen";job["first_seen_at"]=now.isoformat()
        fresh.append(job);seen[key]=now.isoformat()
    save_seen(seen);return fresh,stale,already
