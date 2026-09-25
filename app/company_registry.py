from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH="generated/company_registry.json"

def load(path=DEFAULT_PATH):
    p=Path(path)
    if not p.exists(): return {}
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {}

def save(registry,path=DEFAULT_PATH):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(registry,indent=2,sort_keys=True),encoding="utf-8")

def upsert(registry, company, official_domain=None, careers_url=None, ats_provider=None, ats_identifier=None, discovered_by=None):
    if not company:return
    key=str(company).strip().lower()
    row=registry.setdefault(key,{"company":company})
    for k,v in {"official_domain":official_domain,"careers_url":careers_url,"ats_provider":ats_provider,"ats_identifier":ats_identifier,"discovered_by":discovered_by}.items():
        if v:row[k]=v
    row["last_seen_at"]=datetime.now(timezone.utc).isoformat()

def learn_from_jobs(jobs,registry):
    for j in jobs:
        upsert(registry,j.get("company") or j.get("company_key"),
               careers_url=j.get("original_url") or j.get("url"),
               ats_provider=j.get("ats_provider"),ats_identifier=j.get("ats_identifier"),
               discovered_by=j.get("source"))
    return registry
