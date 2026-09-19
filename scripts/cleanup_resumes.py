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

def _ledger_reference_sets():
    """Return exact referenced files plus job folders implied by those files."""
    exact=set();folders=set()
    ledger=_json(LEDGER,{"jobs":{}})
    for row in (ledger.get("jobs") or {}).values():
        values=[row.get("pdf_path"),row.get("resume_path")]
        for key in ("queue_item","retry_application"):
            payload=row.get(key) or {}
            if isinstance(payload,dict):values.append(payload.get("resume_path"))
        for value in values:
            p=_resolve(value)
            if not p:continue
            exact.add(p)
            try:
                if RESUMES.resolve() in p.parents:folders.add(p.parent.resolve())
            except Exception:pass
    return exact,folders

ACTIVE_APPLICATION_STATUSES={
    # Only states that can be replayed into the ATS automatically must have a
    # recoverable queue/resume artifact. Terminal/manual states are historical
    # application records and may legitimately lack a local resume path.
    "READY_TO_APPLY","APPLICATION_IN_PROGRESS","IN_PROGRESS","RETRY_APPLICATION",
}

def active_application_resume_check():
    """Verify every replayable ATS application has a recoverable protected PDF.

    This mirrors scheduled_runner.APPLICATION_REPLAY_STATUSES. Historical terminal
    states (submitted/manual/security/uncertain) are not replayed automatically and
    therefore are reported elsewhere rather than blocking resume cleanup.
    """
    ledger=_json(LEDGER,{"jobs":{}})
    refs,folders=_ledger_reference_sets()
    rows=[];missing=[]
    for key,row in (ledger.get("jobs") or {}).items():
        status=row.get("application_status") or ""
        if status not in ACTIVE_APPLICATION_STATUSES:continue
        candidates=[row.get("pdf_path"),row.get("resume_path")]
        for name in ("queue_item","retry_application"):
            payload=row.get(name) or {}
            if isinstance(payload,dict):candidates.append(payload.get("resume_path"))
        resolved=[_resolve(x) for x in candidates if x]
        existing=[p for p in resolved if p and p.exists() and p.is_file()]
        protected=[p for p in existing if p.resolve() in refs or p.parent.resolve() in folders]
        item={"key":key,"company":row.get("company"),"title":row.get("title"),"status":status,
              "protected_resume":str(protected[0].relative_to(ROOT)) if protected else None,
              "resume_candidates":[str(p) for p in resolved]}
        rows.append(item)
        if not protected:missing.append(item)
    return rows,missing

def confirmed_resume_names():
    rows=_json(CONFIRMED,{"applications":[]}).get("applications") or []
    return {str(x.get("resume")) for x in rows if x.get("resume")}

def _hash(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def inventory():
    RESUMES.mkdir(parents=True,exist_ok=True)
    refs,ref_folders=_ledger_reference_sets();confirmed=confirmed_resume_names()
    files=[p for p in RESUMES.rglob("*") if p.is_file()]
    hashes={}
    digests={}
    for p in files:
        try:
            d=_hash(p);digests[p]=d;hashes.setdefault(d,[]).append(p)
        except OSError:pass

    rows=[];duplicate_removable=[];orphan_candidates=[]
    for p in files:
        rp=p.resolve();exact=rp in refs;historical=p.name in confirmed
        folder_protected=p.parent.resolve() in ref_folders
        peers=hashes.get(digests.get(p),[])
        protected_peer=next((x for x in peers if x.resolve() in refs or x.name in confirmed),None)
        duplicate=not exact and not historical and protected_peer is not None
        # A file in the same generated job folder as an actively referenced resume
        # is treated as the companion artifact (for example approved DOCX + submitted PDF).
        if exact:status="KEEP_REFERENCED"
        elif historical:status="KEEP_CONFIRMED_HISTORY"
        elif folder_protected:status="KEEP_COMPANION"
        elif duplicate:status="DUPLICATE"
        else:status="ORPHAN_CANDIDATE"
        if duplicate:duplicate_removable.append(p)
        if status=="ORPHAN_CANDIDATE":orphan_candidates.append(p)
        rows.append({"path":str(p.relative_to(ROOT)),"bytes":p.stat().st_size,"status":status,
                     "duplicate_of":str(protected_peer.relative_to(ROOT)) if duplicate else None})

    # A whole folder can be considered an orphan candidate only if every file in
    # that folder is an ORPHAN_CANDIDATE. This remains report-only: --apply never
    # deletes orphan candidates automatically.
    by_folder={}
    for row in rows:
        p=ROOT/row["path"];by_folder.setdefault(p.parent,[]).append(row)
    orphan_folders=[]
    for folder,items in by_folder.items():
        if items and all(x["status"]=="ORPHAN_CANDIDATE" for x in items):
            orphan_folders.append({"path":str(folder.relative_to(ROOT)),"files":len(items),
                                   "bytes":sum(x["bytes"] for x in items)})
    return rows,duplicate_removable,orphan_candidates,orphan_folders

def main():
    ap=argparse.ArgumentParser(description="Inventory and safely deduplicate generated resumes using durable application references.")
    ap.add_argument("--apply",action="store_true",help="Delete only byte-identical unreferenced duplicates; orphan candidates remain untouched.")
    ap.add_argument("--report",default=str(ROOT/"generated"/"resume_cleanup_report.json"))
    args=ap.parse_args()
    rows,removable,orphans,orphan_folders=inventory()
    active,missing=active_application_resume_check()
    counts={}
    for row in rows:counts[row["status"]]=counts.get(row["status"],0)+1
    result={"files":len(rows),"counts":counts,"duplicate_files":len(removable),
            "duplicate_bytes":sum(p.stat().st_size for p in removable),
            "orphan_candidate_files":len(orphans),
            "orphan_candidate_bytes":sum(p.stat().st_size for p in orphans),
            "orphan_candidate_folders":len(orphan_folders),
            "active_application_jobs":len(active),"protected_active_resumes":len(active)-len(missing),
            "missing_active_resumes":len(missing),"applied":False}
    report={"summary":result,"active_applications":active,"missing_active_applications":missing,
            "orphan_folders":orphan_folders,"files":rows}
    report_path=Path(args.report);report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    if args.apply:
        for p in removable:
            if p.exists():p.unlink()
        for p in sorted([x for x in RESUMES.rglob("*") if x.is_dir()],key=lambda x:len(x.parts),reverse=True):
            try:p.rmdir()
            except OSError:pass
        result["applied"]=True
    print(json.dumps(result,indent=2))
    print("\nActive application resume protection:")
    print(f" - replayable jobs: {len(active)}")
    print(f" - protected resumes: {len(active)-len(missing)}")
    print(f" - missing resumes: {len(missing)}")
    for item in missing:
        print(f"   MISSING | {item['status']} | {item['company']} | {item['title']}")
        candidates=item.get("resume_candidates") or []
        if candidates:
            for candidate in candidates:print(f"      candidate: {candidate}")
        else:
            print("      candidate: <no resume path stored in ledger>")
    print("\nOrphan candidate folders (REPORT ONLY; not auto-deleted):")
    for item in orphan_folders:
        print(f" - {item['path']} | {item['files']} file(s) | {item['bytes']} bytes")
    if not orphan_folders:print(" - none")
    print(f"\nDetailed report: {report_path}")
    print("Safety: --apply removes only proven byte-identical duplicates. ORPHAN_CANDIDATE files are never auto-deleted.")

if __name__=="__main__":
    main()
