from __future__ import annotations
import re
from app.resume_generator import jd_keywords

def ats_audit(job, profile, resume_text: str) -> dict:
    verified=jd_keywords(job.description,profile)
    low=resume_text.lower()
    present=[k for k in verified if k.lower() in low]
    missing=[k for k in verified if k.lower() not in low]
    coverage=round(100*len(present)/max(1,len(verified)))
    return {"verified_jd_keywords":verified,"present":present,"missing":missing,"keyword_coverage":coverage,
      "rule":"Missing JD terms are added only when supported by the master resume; unsupported skills are never fabricated."}
