from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import re
ROOT=Path(__file__).resolve().parent.parent
STATE=ROOT/"generated"/"seen_jobs.json"
STATUS=ROOT/"generated"/"job_status.json"

def _parse(v):
    if not v:return None
    try:return datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:return None

def _parse_posting_value(v,now):
    """Parse authoritative posting dates, including ATS relative-age labels."""
    ts=_parse(v)
    if ts is not None:return ts
    text=str(v or "").strip().lower()
    if not text:return None
    if re.fullmatch(r"posted\s+(?:today|just now)",text):return now
    if re.fullmatch(r"posted\s+(?:an?|1)\s+hours?\s+ago",text):return now-timedelta(hours=1)
    m=re.fullmatch(r"posted\s+(\d+)\s+hours?\s+ago",text)
    if m:return now-timedelta(hours=int(m.group(1)))
    if re.fullmatch(r"posted\s+(?:a|1)\s+days?\s+ago",text):return now-timedelta(days=1)
    m=re.fullmatch(r"posted\s+(\d+)\s+days?\s+ago",text)
    if m:return now-timedelta(days=int(m.group(1)))
    return None

def _load(path):
    if not path.exists():return {}
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def load_seen():return _load(STATE)
def load_status():return _load(STATUS)

def save_seen(seen):
    STATE.parent.mkdir(parents=True,exist_ok=True);STATE.write_text(json.dumps(seen,indent=2),encoding="utf-8")

def fresh_jobs(jobs,hours=24,since=None,now=None):
    """Return only jobs with trustworthy posting timestamps inside the requested window.

    Strict mode intentionally does NOT treat first-seen time as proof that a job was
    posted recently. Jobs without a parseable ATS/job-board posting timestamp are
    excluded from automatic processing because the user requires postings from the
    last 24 hours only.
    """
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff=_parse(since) if since else now-timedelta(hours=hours)
    if cutoff is None:cutoff=now-timedelta(hours=hours)
    seen=load_seen();status=load_status();fresh=[];stale=[];already=[]
    terminal={"SUBMITTED","PERMANENT_SKIP"}
    for job in jobs:
        key=job["external_id"]
        if key not in seen:seen[key]=now.isoformat()
        state=status.get(key,{})
        if isinstance(state,str):state={"status":state}
        if state.get("status") in terminal:
            already.append(job);continue
        # Prefer actual publication/posting fields. An ATS updated_at value must not
        # override explicit evidence such as "Posted 3 Days Ago".
        ts=None;basis=None
        posting_fields=("posted_at","posted_on","date_posted","datePosted","published_at","publication_date")
        explicit_posting_present=any(job.get(field) not in (None,"") for field in posting_fields)
        for field in posting_fields:
            ts=_parse_posting_value(job.get(field),now)
            if ts is not None:
                basis=field
                break
        # updated_at is only a last-resort provider timestamp when the source supplied
        # no explicit posting field at all. If explicit posting text exists but cannot
        # be parsed, strict freshness rejects it rather than silently substituting an update time.
        if ts is None and not explicit_posting_present:
            ts=_parse(job.get("updated_at"))
            if ts is not None:basis="updated_at_fallback"
        if ts is None:
            item=dict(job);item["freshness_rejection_reason"]="missing trustworthy posting timestamp"
            stale.append(item);continue
        if ts<cutoff or ts>now+timedelta(minutes=10):
            item=dict(job);item["freshness_rejection_reason"]="outside requested posting window"
            stale.append(item);continue
        job["freshness_basis"]=basis or "source_timestamp"
        fresh.append(job)
    save_seen(seen);return fresh,stale,already
