from __future__ import annotations
import re

NO_SPONSOR_PATTERNS=(
 "without visa sponsorship","without sponsorship","no visa sponsorship",
 "not provide visa sponsorship","does not provide visa sponsorship","do not provide visa sponsorship",
 "unable to sponsor","cannot sponsor","not eligible for sponsorship","must not require sponsorship",
 "will not sponsor","no sponsorship available","not offer sponsorship",
 "no current or future sponsorship","current or future sponsorship is not available",
 "cannot provide current or future sponsorship","will not provide sponsorship"
)
SPONSOR_POSITIVE_PATTERNS=(
 "visa sponsorship is available","sponsorship is available","we sponsor","will sponsor",
 "h-1b sponsorship","h1b sponsorship","employment visa sponsorship","visa transfer"
)

def _clean(v): return re.sub(r"\s+"," ",(v or "").lower()).strip()

def experience_range(text: str):
    text=_clean(text)
    # Require explicit experience context so unrelated values such as "50 years in business"
    # cannot become a candidate experience requirement.
    patterns=(
        r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|hands[- ]on\s+)?experience",
        r"(?:experience|experienced)\s+(?:of\s+)?(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*(?:years?|yrs?)",
    )
    for pattern in patterns:
        m=re.search(pattern,text)
        if m:return int(m.group(1)),int(m.group(2))
    return None

def required_years(text: str):
    text=_clean(text)
    rng=experience_range(text)
    if rng:return rng[0]
    vals=[]
    patterns=(
      r"(?:minimum(?: of)?|min\.?|at least)\s+(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|hands[- ]on\s+)?experience",
      r"(?:requires?|required|requirement:?|qualifications?:?)\s+(?:a\s+)?(?:minimum(?: of)?\s+)?(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|hands[- ]on\s+)?experience",
      r"(\d{1,2})\s*\+\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|hands[- ]on\s+)?(?:[a-z0-9&/+.\-]+\s+){0,5}?experience",
      r"(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|hands[- ]on\s+)?experience\s+(?:required|minimum)",
      r"(?:experience\s+)?min(?:imum)?\.?\s+(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|hands[- ]on\s+)?(?:software\s+engineering\s+)?experience",
    )
    for pattern in patterns:
        vals.extend(int(x) for x in re.findall(pattern,text))
    # Sanity guard: normal DE requirements are single/two-digit, but unrelated company
    # history/age values should never drive eligibility. 15+ is treated as untrusted.
    vals=[x for x in vals if 0 < x <= 15]
    return max(vals) if vals else None

def experience_check(job: dict, profile: dict) -> dict:
    full=f"{job.get('title','')} {job.get('description','')}"
    rng=experience_range(full);req=required_years(full)
    candidate=profile.get("candidate_experience_years",5)
    min_req=profile.get("preferences",{}).get("min_required_years",4)
    max_req=profile.get("preferences",{}).get("max_required_years",8)
    if req is None:
        return {"category":"EXPERIENCE_NOT_STATED","eligible":True,"required_years":None,"candidate_years":candidate,"configured_window":[min_req,max_req]}
    eligible=req <= max_req
    return {
      "category":"EXPERIENCE_ELIGIBLE" if eligible else "EXPERIENCE_TOO_SENIOR",
      "eligible":eligible,"required_years":req,"minimum_years":rng[0] if rng else req,"maximum_years":rng[1] if rng else None,"candidate_years":candidate,"configured_window":[min_req,max_req]
    }

def sponsorship_check(job: dict, profile: dict) -> dict:
    text=_clean(f"{job.get('title','')} {job.get('description','')}")
    needs_future=profile.get("work_authorization",{}).get("requires_sponsorship_future",False)
    if needs_future and any(x in text for x in NO_SPONSOR_PATTERNS):
        return {"category":"NO_SPONSORSHIP","eligible":False,"evidence":"Posting states sponsorship is unavailable."}
    if any(x in text for x in SPONSOR_POSITIVE_PATTERNS):
        return {"category":"SPONSORSHIP_AVAILABLE","eligible":True,"evidence":"Posting contains affirmative sponsorship language."}
    return {"category":"SPONSORSHIP_UNKNOWN","eligible":None,"evidence":"Sponsorship policy is not explicit in the posting; continue under candidate policy."}

def two_category_filter(job: dict, profile: dict) -> dict:
    exp=experience_check(job,profile); sponsor=sponsorship_check(job,profile)
    eligible=exp["eligible"] and sponsor["eligible"] is not False
    return {"eligible":eligible,"experience":exp,"sponsorship":sponsor}
