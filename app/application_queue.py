from __future__ import annotations
import argparse,json
from pathlib import Path
def build(manifest_path="generated/application_manifest.json",output="generated/application_queue.json"):
    rows=json.loads(Path(manifest_path).read_text(encoding="utf-8"));queue=[]
    for r in rows:
        if r.get("next_action")!="READY_TO_APPLY":continue
        resume=r.get("pdf_path") or r.get("resume_path")
        if not resume:continue
        queue.append({"external_id":r.get("external_id"),"source":r.get("source"),"company":r.get("company"),"title":r.get("title"),"url":r.get("url"),"ats_score":r.get("ats_audit",{}).get("internal_ats_score"),"resume_path":resume,"authorized_to_work_us":"Yes","requires_future_sponsorship":"Yes","sponsorship_statement":"I am currently authorized to work in the United States under F-1 OPT and do not require sponsorship at this time. I will require H-1B sponsorship in the future to continue working in the United States.","status":"READY_FOR_ATS_ADAPTER"})
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(queue,indent=2),encoding="utf-8");return queue
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--manifest",default="generated/application_manifest.json");p.add_argument("--output",default="generated/application_queue.json");a=p.parse_args();rows=build(a.manifest,a.output);print(json.dumps({"queued":len(rows),"output":a.output},indent=2))
