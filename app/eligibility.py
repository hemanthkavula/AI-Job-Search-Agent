from __future__ import annotations
import re

NO_SPONSOR_PATTERNS=(
 "without visa sponsorship","without sponsorship","no visa sponsorship",
 "not provide visa sponsorship","does not provide visa sponsorship","do not provide visa sponsorship",
 "unable to sponsor","cannot sponsor","not eligible for sponsorship","must not require sponsorship",
 "will not sponsor","no sponsorship available","not offer sponsorship"
)
SPONSOR_POSITIVE_PATTERNS=(
 "visa sponsorship is available","sponsorship is available","we sponsor","will sponsor",
 "h-1b sponsorship","h1b sponsorship","employment visa sponsorship","visa transfer"
)

def _clean(v): return re.sub(r"\s+"," ",(v or "").lower()).strip()

def experience_range(text: str):
    text=_clean(text)
    ranges=[(int(a),int(b)) for a,b in re.findall(r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*(?:years?|yrs?)",text)]
    return ranges[0] if ranges else None

def required_years(text: str):
    text=_clean(text)
    rng=experience_range(text)
    if rng:return rng[0]
    vals=[]
    patterns=(
      r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+)?experience",
      r"(?:minimum|min\.?|at least)\s+(\d{1,2})\s*(?:years?|yrs?)"
    )
    for pattern in patterns:
        vals.extend(int(x) for x in re.findall(pattern,text))
    return max(vals) if vals else None

def experience_check(job: dict, profile: dict) -> dict:
    full=f"{job.get('title','')} {job.get('description','')}"
    rng=experience_range(full);req=required_years(full)
    candidate=profile.get("candidate_experience_years",5)
    min_req=profile.get("preferences",{}).get("min_required_years",4)
    max_req=profile.get("preferences",{}).get("max_required_years",8)
    if req is None:
        return {"category":"EXPERIENCE_NOT_STATED","eligible":True,"required_years":None,"candidate_years":candidate,"configured_window":[min_req,max_req]}
    # Accept roles whose stated minimum is at or below the user's 8-year ceiling.
    # A 3-5 year role is still appropriate for a 5-year candidate; 9+/10+/12+ is not.
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
    return {"category":"SPONSORSHIP_UNKNOWN","eligible":None,"evidence":"Sponsorship policy is not explicit in the posting; verify before submission."}

def two_category_filter(job: dict, profile: dict) -> dict:
    exp=experience_check(job,profile); sponsor=sponsorship_check(job,profile)
    eligible=exp["eligible"] and sponsor["eligible"] is not False
    return {"eligible":eligible,"experience":exp,"sponsorship":sponsor}
