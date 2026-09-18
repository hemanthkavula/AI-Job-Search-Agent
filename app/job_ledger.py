from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from app.job_identity import canonical_job_key

DEFAULT_LEDGER=Path("generated/job_ledger.json")

def load_ledger(path=DEFAULT_LEDGER):
    p=Path(path)
    if not p.exists():return {"jobs":{}}
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {"jobs":{}}

def save_ledger(ledger,path=DEFAULT_LEDGER):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(ledger,indent=2),encoding="utf-8")

def seen_or_submitted(job,ledger):
    key=canonical_job_key(job);row=ledger.get("jobs",{}).get(key)
    return bool(row and row.get("application_status") in {"SUBMITTED","READY_TO_APPLY","IN_PROGRESS"}),key,row

def record_seen(job,ledger,status="DISCOVERED",**extra):
    key=canonical_job_key(job);now=datetime.now(timezone.utc).isoformat()
    jobs=ledger.setdefault("jobs",{});row=jobs.setdefault(key,{"first_seen":now})
    row.update({"last_seen":now,"company":job.get("company_key") or job.get("company"),"title":job.get("title"),
                "source":job.get("source"),"url":job.get("original_url") or job.get("url"),"application_status":status})
    row.update(extra);return key
