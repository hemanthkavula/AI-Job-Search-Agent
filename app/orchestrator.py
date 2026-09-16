from __future__ import annotations
from types import SimpleNamespace
from app.config import load_profile
from app.filters import passes_hard_filters
from app.scoring import analyze_job
from app.resume_generator import generate_resume
from app.db import save_job
from app.application_queue import enqueue

def process_job(raw: dict, min_score: int=70) -> dict:
    """One pipeline: filter -> score -> resume -> review queue."""
    profile=load_profile()
    ok,reasons=passes_hard_filters(raw,profile)
    if not ok:
        return {"status":"FILTERED","reasons":reasons}

    job=SimpleNamespace(
        company=raw.get("company") or raw.get("company_key") or "Unknown",
        title=raw.get("title") or "",
        description=raw.get("description") or "",
        location=raw.get("location"),
        employment_type=raw.get("employment_type"),
        url=raw.get("url"),
    )
    analysis=analyze_job(job,profile)
    if analysis["score"] < min_score:
        return {"status":"LOW_SCORE","analysis":analysis}

    resume_path=generate_resume(job,analysis,profile)
    application_id=save_job(job,analysis)
    queue_id=enqueue(application_id,resume_path)
    return {
        "status":"READY_FOR_REVIEW",
        "application_id":application_id,
        "queue_id":queue_id,
        "analysis":analysis,
        "resume_path":resume_path,
        "job_url":job.url,
    }
