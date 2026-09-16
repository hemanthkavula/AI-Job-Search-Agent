from __future__ import annotations
import re

EXCLUDED_TITLE_TERMS={"analyst","scientist","frontend","front end","qa engineer","business intelligence","power bi developer","tableau developer"}
EXCLUDED_EMPLOYMENT_TERMS={"c2c","corp-to-corp","corp to corp","1099 only"}
NO_SPONSOR_PATTERNS=(
 "without visa sponsorship","without sponsorship","no visa sponsorship",
 "not provide visa sponsorship","does not provide visa sponsorship",
 "do not provide visa sponsorship","unable to sponsor","cannot sponsor",
 "not eligible for sponsorship","must not require sponsorship",
 "will not sponsor","no sponsorship available"
)
NON_US_LOCATION_TERMS=("south america","latin america","canada only","uk only","united kingdom","india only","europe only","emea","apac")

def _clean(v): return re.sub(r"\s+"," ",(v or "").lower()).strip()

def _required_years(text: str):
    vals=[]
    for m in re.finditer(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+)?experience",text):
        vals.append(int(m.group(1)))
    return max(vals) if vals else None

def passes_hard_filters(job: dict,profile: dict):
    title=_clean(job.get("title")); desc=_clean(job.get("description")); loc=_clean(job.get("location")); reasons=[]
    targets=[_clean(x) for x in profile["preferences"]["target_roles"]]
    if not any(t in title or title in t for t in targets) and not ("data" in title and ("engineer" in title or "platform" in title)):
        reasons.append("title outside configured data-engineering targets")
    if any(x in title for x in EXCLUDED_TITLE_TERMS): reasons.append("excluded title category")
    combined=f"{title} {desc}"
    if any(x in combined for x in EXCLUDED_EMPLOYMENT_TERMS): reasons.append("C2C/1099-only language detected")

    wa=profile.get("work_authorization",{})
    if wa.get("requires_sponsorship_future") and any(x in combined for x in NO_SPONSOR_PATTERNS):
        reasons.append("employer states visa sponsorship is unavailable")

    if any(x in loc for x in NON_US_LOCATION_TERMS):
        reasons.append("location is outside configured US search")

    max_years=profile.get("preferences",{}).get("max_required_years")
    req=_required_years(combined)
    if max_years and req and req>max_years:
        reasons.append(f"job requires {req}+ years; configured maximum is {max_years}")

    return len(reasons)==0,reasons
