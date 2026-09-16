from __future__ import annotations
import re
from app.eligibility import two_category_filter

# Strictly data-engineering job families. Do not admit generic platform/software/data roles.
ALLOWED_TITLE_PATTERNS=[
 r"\bdata engineer\b",r"\bsenior data engineer\b",r"\bsr\.? data engineer\b",
 r"\blead data engineer\b",r"\bprincipal data engineer\b",r"\bstaff data engineer\b",
 r"\baws data engineer\b",r"\bazure data engineer\b",r"\bcloud data engineer\b",
 r"\bbig data engineer\b",r"\bdata platform engineer\b",r"\bdata infrastructure engineer\b",
 r"\bdata pipeline engineer\b",r"\betl data engineer\b",r"\banalytics data engineer\b"
]
EXCLUDED_TITLE_TERMS={"analyst","scientist","frontend","front end","qa engineer","business intelligence","power bi developer","tableau developer","software engineer","machine learning engineer","devops engineer","site reliability","database administrator","data architect","solutions architect","product manager"}

def _clean(v):return re.sub(r"\s+"," ",(v or "").lower()).strip()
def title_is_target(title):
    t=_clean(title)
    if any(x in t for x in EXCLUDED_TITLE_TERMS):return False
    return any(re.search(p,t) for p in ALLOWED_TITLE_PATTERNS)

def passes_hard_filters(job:dict,profile:dict):
    title=_clean(job.get("title"));reasons=[]
    if not title_is_target(title):reasons.append("title outside strict data-engineering job family")
    eligibility=two_category_filter(job,profile)
    if not eligibility["experience"]["eligible"]:reasons.append(f"experience requirement not met: {eligibility['experience']['required_years']} years required")
    if eligibility["sponsorship"]["eligible"] is False:reasons.append("future H-1B sponsorship unavailable")
    return len(reasons)==0,reasons
