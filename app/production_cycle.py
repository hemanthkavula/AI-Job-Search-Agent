from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from app.daily_runner import run as discover_and_filter
from app.jd_finalizer import finalize_report
from app.batch_prepare import prepare
from app.job_ledger import load_ledger,save_ledger,record_seen,retryable_jobs,retry_metadata,_lookup
from app.application_queue import build as build_application_queue

ROOT=Path(__file__).resolve().parent.parent

def _write(path,payload):
 p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(payload,indent=2),encoding="utf-8");return str(p)

def _sync_finalized(rows,ledger_path,cycle_id=None):
 ledger=load_ledger(ledger_path)
 for row in rows:
  raw=row.get("job") or row.get("raw") or row
  status=row.get("action") or raw.get("action")
  if not status:continue
  record_seen(raw,ledger,status,
              original_url=raw.get("original_url"),
              ats_provider=raw.get("ats_provider"),
              ats_identifier=raw.get("ats_identifier"),
              requisition_id=raw.get("requisition_id") or raw.get("job_id"),
              jd_hash=raw.get("jd_hash"),
              description_complete=raw.get("description_complete"),
              cycle_id=cycle_id)
 save_ledger(ledger,ledger_path)

def _retry_items_from_ledger(ledger_path):
 ledger_data=load_ledger(ledger_path)
 items=[]
 for raw in retryable_jobs(ledger_data):
  elig=raw.get("eligibility")
  if not isinstance(elig,dict):continue
  items.append({"action":"FINAL_JD_VERIFIED","job":raw,"eligibility":elig})
 return items

def _sync_manifest(rows,ledger_path,cycle_id=None):
 ledger=load_ledger(ledger_path)
 for row in rows:
  job={"external_id":row.get("external_id"),"source":row.get("source"),"company_key":row.get("company"),"title":row.get("title"),"url":row.get("url")}
  extra={"resume_path":row.get("resume_path"),"pdf_path":row.get("pdf_path"),"ats_audit":row.get("ats_audit"),"artifact_validation":row.get("artifact_validation"),"cycle_id":cycle_id}
  status=row.get("next_action") or "PREPARED"
  if row.get("next_action")=="READY_TO_APPLY":
   pdf_path=row.get("pdf_path")
   validation=row.get("artifact_validation") or {}
   explicit_validation="artifact_validation" in row and row.get("artifact_validation") is not None
   if pdf_path and Path(pdf_path).suffix.lower()==".pdf" and (not explicit_validation or validation.get("passed")):
    queue_payload={
     "external_id":row.get("external_id"),"source":row.get("source"),"company":row.get("company"),"title":row.get("title"),
     "url":row.get("original_url") or row.get("url"),"ats_provider":row.get("ats_provider"),"application_route":row.get("application_route"),
     "resume_path":pdf_path,"artifact_validation":row.get("artifact_validation"),
     "status":"READY_FOR_ATS_ADAPTER",
    }
    if queue_payload.get("external_id"):extra["queue_item"]=queue_payload
   else:
    status="HOLD_ARTIFACT_VALIDATION"
    extra["queue_item"]=None
    extra["application_reason"]="Validated PDF resume is required before application."
  if row.get("next_action")=="RETRY_RESUME_GENERATION":
   _,existing=_lookup(job,ledger)
   meta=retry_metadata(existing or {},"resume")
   extra.update(meta)
   if meta["resume_retry_exhausted"]:
    status="MANUAL_ACTION_REQUIRED"
    extra["retry_job"]=None
    extra["retry_exhausted_reason"]="Resume generation retry limit reached"
   else:
    extra["retry_job"]={
    "external_id":row.get("external_id"),"source":row.get("source"),"company_key":row.get("company"),"title":row.get("title"),
    "url":row.get("url"),"original_url":row.get("original_url"),"ats_provider":row.get("ats_provider"),"ats_identifier":row.get("ats_identifier"),
    "ats_resolution":row.get("ats_resolution"),"application_route":row.get("application_route"),"tailoring_mode":row.get("tailoring_mode"),
    "description":row.get("description"),"description_complete":row.get("description_complete"),"description_usable":row.get("description_usable"),
    "employment_type":row.get("employment_type"),"location":row.get("location"),"eligibility":row.get("eligibility")
    }
  record_seen(job,ledger,status,**extra)
 save_ledger(ledger,ledger_path)

def run_cycle(sources="data/job_sources.json",hours=24,ledger="generated/job_ledger.json",generate_resumes=False,limit=None,external_id=None,since=None,scan_now=None,source_since=None,source_hours=None,source_unit_hours=None):
 stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
 eligible_rel=f"generated/cycles/{stamp}_eligible.json"
 finalized_rel=f"generated/cycles/{stamp}_finalized.json"
 manifest_rel=f"generated/cycles/{stamp}_manifest.json"
 queue_rel=f"generated/cycles/{stamp}_application_queue.json"
 discovery=discover_and_filter(sources,hours,ledger_path=ledger,since=since,scan_now=scan_now,source_since=source_since,source_hours=source_hours,source_unit_hours=source_unit_hours)
 _write(eligible_rel,discovery)
 finalized=finalize_report(str(ROOT/eligible_rel),str(ROOT/finalized_rel))
 _sync_finalized(finalized.get("jobs") or finalized.get("results") or [],ledger,stamp)
 retry_items=_retry_items_from_ledger(ledger) if generate_resumes else []
 finalized_results=list(finalized.get("results") or finalized.get("jobs") or [])
 retry_ids={x["job"].get("external_id") for x in retry_items}
 existing_ids={(x.get("job") or {}).get("external_id") for x in finalized_results}
 for item in retry_items:
  if item["job"].get("external_id") not in existing_ids:
   finalized_results.append(item)
 if retry_items:
  finalized["results"]=finalized_results
  finalized["finalized"]=sum(1 for x in finalized_results if x.get("action")=="FINAL_JD_VERIFIED")
  _write(finalized_rel,finalized)
 manifest=[]
 if generate_resumes and finalized.get("finalized"):
  manifest=prepare(str(ROOT/finalized_rel),str(ROOT/manifest_rel),external_id=external_id,limit=limit)
  _sync_manifest(manifest,ledger,stamp)
 queue=build_application_queue(str(ROOT/manifest_rel),str(ROOT/queue_rel)) if manifest else []
 # Dashboard-facing eligibility is intentionally the final application-ready
 # count. Preliminary filter matches remain available in the eligible report,
 # but are not presented as "eligible" until JD/live-route verification,
 # resume generation, and artifact validation have all succeeded.
 ready_count=sum(x.get("next_action")=="READY_TO_APPLY" for x in manifest)
 summary={"cycle_id":stamp,"scan_window_hours":hours,"discovered":discovery.get("discovered",0),"eligible":ready_count,
          "preliminary_eligible":discovery.get("eligible",0),
          "final_jd_verified":finalized.get("finalized",0),"held_or_rejected":finalized.get("held_or_rejected",0),
          "resume_generation_enabled":generate_resumes,"prepared":len(manifest),
          "ready_to_apply":ready_count,
          "manual_ready_to_apply":sum(x.get("next_action")=="MANUAL_READY_TO_APPLY" for x in manifest),
          "hold_ats_review":sum(x.get("next_action")=="HOLD_ATS_REVIEW" for x in manifest),
          "hold_artifact_validation":sum(x.get("next_action")=="HOLD_ARTIFACT_VALIDATION" for x in manifest),
          "retry_resume_generation":sum(x.get("next_action")=="RETRY_RESUME_GENERATION" for x in manifest),
          "eligible_report":eligible_rel,"finalized_report":finalized_rel,
          "manifest":manifest_rel if generate_resumes else None,
          "application_queue":queue_rel if manifest else None,
          "queued_for_application":sum(x.get("status")=="READY_FOR_ATS_ADAPTER" for x in queue),
          "manual_application_action":sum(x.get("status")=="MANUAL_ACTION_REQUIRED" for x in queue),"source_status":discovery.get("source_status",{}),
          "source_errors":discovery.get("source_errors",{}),"source_unit_status":discovery.get("source_unit_status",{})}
 _write(f"generated/cycles/{stamp}_summary.json",summary)
 return summary

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--sources",default="data/job_sources.json");p.add_argument("--hours",type=int,default=24)
 p.add_argument("--ledger",default="generated/job_ledger.json")
 p.add_argument("--generate-resumes",action="store_true",help="Enable paid LLM resume generation. Omit for free discovery/finalization dry runs.")
 p.add_argument("--limit",type=int,help="Optional resume-generation cap for controlled validation.")
 p.add_argument("--external-id",help="Generate a resume only for the matching finalized job external_id.")
 a=p.parse_args();print(json.dumps(run_cycle(a.sources,a.hours,a.ledger,a.generate_resumes,a.limit,a.external_id),indent=2))
