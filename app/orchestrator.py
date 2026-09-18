from __future__ import annotations
from types import SimpleNamespace
from app.config import load_profile
from app.filters import passes_hard_filters
from app.eligibility import two_category_filter
from app.scoring import analyze_job
from app.resume_generator import generate_resume
from app.db import save_job

def process_job(raw: dict,min_score: int=65) -> dict:
    profile=load_profile()
    eligibility=two_category_filter(raw,profile)
    ok,reasons=passes_hard_filters(raw,profile)
    if not ok: return {"status":"FILTERED","reasons":reasons,"eligibility":eligibility}

    job=SimpleNamespace(company=raw.get("company") or raw.get("company_key") or "Unknown",
      title=raw.get("title") or "",description=raw.get("description") or "",
      location=raw.get("location"),employment_type=raw.get("employment_type"),url=raw.get("url"))
    analysis=analyze_job(job,profile)
    if analysis["score"]<min_score:
        return {"status":"LOW_SCORE","analysis":analysis,"eligibility":eligibility}

    resume_path=generate_resume(job,analysis,profile)
    application_id=save_job(job,analysis)
    # Legacy single-job API path: keep the generated resume linked to the saved
    # application record without depending on the production manifest queue.
    return {"status":"READY_FOR_REVIEW","application_id":application_id,
      "analysis":analysis,"eligibility":eligibility,"resume_path":resume_path,"job_url":job.url}
