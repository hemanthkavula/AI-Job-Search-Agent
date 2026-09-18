from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from app.daily_runner import run as discover_and_filter
from app.jd_finalizer import finalize_report
from app.batch_prepare import prepare
from app.job_ledger import load_ledger,save_ledger,record_seen

ROOT=Path(__file__).resolve().parent.parent

def _write(path,payload):
 p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(payload,indent=2),encoding="utf-8");return str(p)

def _sync_finalized(rows,ledger_path):
 ledger=load_ledger(ledger_path)
 for row in rows:
  raw=row.get("raw") or row
  status=row.get("action") or raw.get("action")
  if not status:continue
  record_seen(raw,ledger,status,
              original_url=raw.get("original_url"),
              ats_provider=raw.get("ats_provider"),
              ats_identifier=raw.get("ats_identifier"),
              requisition_id=raw.get("requisition_id") or raw.get("job_id"),
              jd_hash=raw.get("jd_hash"),
              description_complete=raw.get("description_complete"))
 save_ledger(ledger,ledger_path)

def _sync_manifest(rows,ledger_path):
 ledger=load_ledger(ledger_path)
 for row in rows:
  job={"external_id":row.get("external_id"),"source":row.get("source"),"company_key":row.get("company"),"title":row.get("title"),"url":row.get("url")}
  record_seen(job,ledger,row.get("next_action") or "PREPARED",resume_path=row.get("resume_path"),pdf_path=row.get("pdf_path"),ats_audit=row.get("ats_audit"))
 save_ledger(ledger,ledger_path)

def run_cycle(sources="data/job_sources.json",hours=24,ledger="generated/job_ledger.json",generate_resumes=False,limit=None):
 stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
 eligible_rel=f"generated/cycles/{stamp}_eligible.json"
 finalized_rel=f"generated/cycles/{stamp}_finalized.json"
 manifest_rel=f"generated/cycles/{stamp}_manifest.json"
 discovery=discover_and_filter(sources,hours,ledger_path=ledger)
 _write(eligible_rel,discovery)
 finalized=finalize_report(str(ROOT/eligible_rel),str(ROOT/finalized_rel))
 _sync_finalized(finalized.get("jobs") or finalized.get("results") or [],ledger)
 manifest=[]
 if generate_resumes and finalized.get("finalized"):
  manifest=prepare(str(ROOT/finalized_rel),str(ROOT/manifest_rel),limit=limit)
  _sync_manifest(manifest,ledger)
 summary={"cycle_id":stamp,"discovered":discovery.get("discovered",0),"eligible":discovery.get("eligible",0),
          "final_jd_verified":finalized.get("finalized",0),"held_or_rejected":finalized.get("held_or_rejected",0),
          "resume_generation_enabled":generate_resumes,"prepared":len(manifest),
          "ready_to_apply":sum(x.get("next_action")=="READY_TO_APPLY" for x in manifest),
          "hold_ats_review":sum(x.get("next_action")=="HOLD_ATS_REVIEW" for x in manifest),
          "eligible_report":eligible_rel,"finalized_report":finalized_rel,
          "manifest":manifest_rel if generate_resumes else None}
 _write(f"generated/cycles/{stamp}_summary.json",summary)
 return summary

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--sources",default="data/job_sources.json");p.add_argument("--hours",type=int,default=24)
 p.add_argument("--ledger",default="generated/job_ledger.json")
 p.add_argument("--generate-resumes",action="store_true",help="Enable paid LLM resume generation. Omit for free discovery/finalization dry runs.")
 p.add_argument("--limit",type=int,help="Optional resume-generation cap for controlled validation.")
 a=p.parse_args();print(json.dumps(run_cycle(a.sources,a.hours,a.ledger,a.generate_resumes,a.limit),indent=2))
