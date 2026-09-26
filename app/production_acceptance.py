from __future__ import annotations
import argparse, json
from urllib.parse import urlparse
from pathlib import Path

def audit(summary_path:str)->dict:
    p=Path(summary_path)
    summary=json.loads(p.read_text(encoding="utf-8"))
    failures=[]
    ready=int(summary.get("ready_to_apply") or 0)
    queued=int(summary.get("queued_for_application") or 0)
    eligible=int(summary.get("eligible") or 0)
    manifest_ready=int(summary.get("manifest_ready_to_apply") or 0)
    if not (ready==queued==eligible):
        failures.append(f"ready/queued/eligible mismatch: {ready}/{queued}/{eligible}")
    if ready>manifest_ready:
        failures.append(f"queued ready exceeds validated manifest ready: {ready}>{manifest_ready}")
    if summary.get("resume_generation_enabled") and summary.get("prepared",0)<manifest_ready:
        failures.append("manifest ready exceeds prepared artifacts")
    if int(summary.get("manual_application_action") or 0):
        failures.append("manual application state is not allowed in the ready-only production flow")
    queue_path=summary.get("application_queue")
    if ready:
        if not queue_path or not Path(queue_path).exists():
            failures.append("ready jobs exist but application queue is missing")
        else:
            queue=json.loads(Path(queue_path).read_text(encoding="utf-8"))
            if len(queue)!=ready:
                failures.append(f"queue length mismatch: {len(queue)}!={ready}")
            ids=set()
            for row in queue:
                eid=row.get("external_id")
                if not eid or eid in ids: failures.append(f"duplicate/missing queue external_id: {eid}")
                ids.add(eid)
                if row.get("status")!="READY_FOR_ATS_ADAPTER": failures.append(f"invalid queue status for {eid}")
                url=row.get("url") or ""
                host=(urlparse(url).netloc or "").lower()
                aggregator_hosts=("dice.com","indeed.com","linkedin.com","ziprecruiter.com","monster.com","wellfound.com","builtin.com","ycombinator.com")
                if not url or any(host==h or host.endswith("."+h) for h in aggregator_hosts):
                    failures.append(f"non-authoritative application destination for {eid}: {host or 'missing'}")
                if not (row.get("application_gate") or {}).get("passed"): failures.append(f"application gate not passed for {eid}")
                resume=row.get("resume_path")
                if not resume or Path(resume).suffix.lower()!=".pdf" or not Path(resume).is_file(): failures.append(f"validated PDF missing for {eid}")
                validation=row.get("artifact_validation")
                if validation and not validation.get("passed"): failures.append(f"artifact validation failed for {eid}")
    result={"passed":not failures,"cycle_id":summary.get("cycle_id"),"ready_to_apply":ready,"failures":failures}
    out=p.with_name(p.stem+"_acceptance.json")
    out.write_text(json.dumps(result,indent=2),encoding="utf-8")
    if failures: raise SystemExit("Production acceptance failed: "+" | ".join(failures))
    print(json.dumps(result,indent=2))
    return result

def latest_summary(root="generated/cycles")->Path:
    rows=sorted(Path(root).glob("*_summary.json"))
    if not rows: raise SystemExit("No production cycle summary found")
    return rows[-1]

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--summary")
    a=ap.parse_args();audit(a.summary or str(latest_summary()))
