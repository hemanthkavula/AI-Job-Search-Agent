from __future__ import annotations
import json,re
from pathlib import Path

DEFAULT_PATH=Path("data/target_companies.json")

def _norm(value):
    return re.sub(r"[^a-z0-9]+"," ",(value or "").lower()).strip()

def load_targets(path=DEFAULT_PATH):
    p=Path(path)
    if not p.exists(): return {"companies":[]}
    return json.loads(p.read_text(encoding="utf-8"))

def target_index(payload=None):
    payload=payload or load_targets()
    index={}
    for row in payload.get("companies",[]):
        names=[row.get("company"),*(row.get("aliases") or [])]
        for name in names:
            key=_norm(name)
            if key:index[key]=row
    return index

def match_target(company,payload=None):
    key=_norm(company)
    if not key:return None
    index=target_index(payload)
    if key in index:return index[key]
    # Conservative containment supports ATS company suffixes such as "Capital One, N.A."
    # without making short aliases match unrelated employers.
    candidates=[]
    for name,row in index.items():
        if len(name)>=6 and (name in key or key in name):
            candidates.append((len(name),row))
    return max(candidates,key=lambda x:x[0])[1] if candidates else None

def annotate_jobs(jobs,payload=None):
    payload=payload or load_targets()
    for job in jobs:
        company=job.get("company") or job.get("company_key") or ""
        target=match_target(company,payload)
        job["target_company"]=bool(target)
        if target:
            job["target_company_name"]=target.get("company")
            job["target_categories"]=target.get("categories") or []
    return jobs
