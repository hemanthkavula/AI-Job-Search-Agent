from __future__ import annotations
import re
from app.eligibility import two_category_filter

EXCLUDED_TITLE_TERMS={"analyst","scientist","frontend","front end","qa engineer","business intelligence","power bi developer","tableau developer"}

def _clean(v): return re.sub(r"\s+"," ",(v or "").lower()).strip()

def passes_hard_filters(job: dict,profile: dict):
    """Only target-role + the two requested eligibility categories: experience and sponsorship."""
    title=_clean(job.get("title")); reasons=[]
    targets=[_clean(x) for x in profile["preferences"]["target_roles"]]
    if not any(t in title or title in t for t in targets) and not ("data" in title and ("engineer" in title or "platform" in title)):
        reasons.append("title outside configured data-engineering targets")
    if any(x in title for x in EXCLUDED_TITLE_TERMS): reasons.append("excluded title category")

    eligibility=two_category_filter(job,profile)
    if not eligibility["experience"]["eligible"]:
        reasons.append(f"experience requirement not met: {eligibility['experience']['required_years']} years required")
    if eligibility["sponsorship"]["eligible"] is False:
        reasons.append("future H-1B sponsorship unavailable")

    return len(reasons)==0,reasons
