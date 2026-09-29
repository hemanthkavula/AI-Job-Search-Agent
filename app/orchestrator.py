from __future__ import annotations
from types import SimpleNamespace
from app.config import load_profile
from app.filters import passes_hard_filters
from app.eligibility import two_category_filter
from app.scoring import analyze_job
from app.resume_generator import generate_resume
from app.db import save_job

def process_job(raw: dict,min_score: int=65) -> dict:
    """Legacy single-job analysis endpoint.

    This path intentionally cannot generate application-ready artifacts. Production
    readiness requires the canonical discovery -> freshness -> official ATS/JD ->
    final eligibility -> audited resume -> artifact -> application-queue pipeline.
    Keeping this endpoint analysis-only prevents a second, weaker eligibility path
    from bypassing those gates.
    """
    profile=load_profile()
    eligibility=two_category_filter(raw,profile)
    ok,reasons=passes_hard_filters(raw,profile)
    if not ok:return {"status":"FILTERED","reasons":reasons,"eligibility":eligibility}
    job=SimpleNamespace(company=raw.get("company") or raw.get("company_key") or "Unknown",
      title=raw.get("title") or "",description=raw.get("description") or "",
      location=raw.get("location"),employment_type=raw.get("employment_type"),url=raw.get("url"))
    analysis=analyze_job(job,profile)
    if analysis["score"]<min_score:
        return {"status":"LOW_SCORE","analysis":analysis,"eligibility":eligibility}
    return {"status":"REQUIRES_PRODUCTION_PIPELINE","analysis":analysis,"eligibility":eligibility,
      "job_url":job.url,"reason":"Official ATS, freshness, final-JD, resume-audit and artifact gates are required before readiness."}
