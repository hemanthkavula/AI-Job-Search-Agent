from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

RESUMES=ROOT/"generated"/"resumes"
LEDGER=ROOT/"generated"/"job_ledger.json"
CONFIRMED=ROOT/"data"/"confirmed_applications.json"

def _json(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def _resolve(value):
    if not value:return None
    p=Path(value)
    if not p.is_absolute():p=ROOT/p
    try:return p.resolve()
    except Exception:return p

def referenced_resume_paths():
    """Return exact resume artifacts referenced by durable application state."""
    refs=set()
    ledger=_json(LEDGER,{"jobs":{}})
    for row in (ledger.get("jobs") or {}).values():
        values=[row.get("pdf_path"),row.get("resume_path")]
        for key in ("queue_item","retry_application"):
            payload=row.get(key) or {}
            if isinstance(payload,dict):values.append(payload.get("resume_path"))
        for value in values:
            p=_resolve(value)
            if p:refs.add(p)
    return refs

def confirmed_resume_names():
    """Historical confirmations may retain a filename even when an old path is absent."""
    rows=_json(CONFIRMED,{"applications":[]}).get("applications") or []
    return {str(x.get("resume")) for x in rows if x.get("resume")}

def _hash(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def inventory():
    RESUMES.mkdir(parents=True,exist_ok=True)
    refs=referenced_resume_paths();confirmed=confirmed_resume_names()
    files=[p for p in RESUMES.rglob("*") if p.is_file()]
    hashes={}
    for p in files:
        try:hashes.setdefault(_hash(p),[]).append(p)
        except OSError:pass
    rows=[];removable=[]
    for p in files:
        rp=p.resolve()
        exact=rp in refs
        historical=p.name in confirmed
        try:digest=_hash(p)
        except OSError:digest=None
        peers=hashes.get(digest,[]) if digest else []
        # A duplicate is removable only when another byte-identical copy exists
        # and this exact path is not referenced or named in confirmed history.
        protected_peer=next((x for x in peers if x.resolve() in refs or x.name in confirmed),None)
        duplicate=not exact and not historical and protected_peer is not None
        status="KEEP_REFERENCED" if exact else "KEEP_CONFIRMED_HISTORY" if historical else "DUPLICATE" if duplicate else "KEEP_UNPROVEN"
        if duplicate:removable.append(p)
        rows.append({"path":str(p.relative_to(ROOT)),"bytes":p.stat().st_size,"status":status,
                     "duplicate_of":str(protected_peer.relative_to(ROOT)) if duplicate else None})
    empty=[p for p in RESUMES.rglob("*") if p.is_dir() and not any(p.iterdir())]
    return rows,removable,empty

def main():
    ap=argparse.ArgumentParser(description="Safely inventory/deduplicate generated resumes using durable application references.")
    ap.add_argument("--apply",action="store_true",help="Delete only byte-identical unreferenced duplicates and empty folders.")
    args=ap.parse_args()
    rows,removable,empty=inventory()
    counts={}
    for row in rows:counts[row["status"]]=counts.get(row["status"],0)+1
    result={"files":len(rows),"counts":counts,"duplicate_files":len(removable),
            "duplicate_bytes":sum(p.stat().st_size for p in removable),"empty_folders":len(empty),"applied":False}
    if args.apply:
        for p in removable:
            if p.exists():p.unlink()
        # deepest first; only remove folders that are actually empty after file cleanup
        for p in sorted([x for x in RESUMES.rglob("*") if x.is_dir()],key=lambda x:len(x.parts),reverse=True):
            try:p.rmdir()
            except OSError:pass
        result["applied"]=True
    print(json.dumps(result,indent=2))
    print("\nCandidates:")
    for row in rows:
        if row["status"]=="DUPLICATE":
            print(f" - {row['path']} -> duplicate of {row['duplicate_of']}")
    if not removable:print(" - none")
    print("\nSafety: KEEP_UNPROVEN files are intentionally not deleted.")

if __name__=="__main__":
    main()
