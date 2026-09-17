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

US_MARKERS={"united states","united states of america","usa","u.s.","u.s.a.","us remote","remote - us","remote, us","remote us"}
NON_US_MARKERS={
 "romania","bucharest","canada","toronto","vancouver","india","bangalore","bengaluru","hyderabad","pune","chennai","mumbai","delhi",
 "united kingdom","london","ireland","dublin","germany","berlin","munich","france","paris","spain","madrid","netherlands","amsterdam",
 "poland","warsaw","portugal","lisbon","italy","milan","australia","sydney","melbourne","singapore","japan","tokyo","mexico","brazil"
}
US_STATE_RE=re.compile(r"(?:^|[,|\s])(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)(?:\s|,|\||$)",re.I)

def _clean(v):return re.sub(r"\s+"," ",(v or "").lower()).strip()
def title_is_target(title):
    t=_clean(title)
    if any(x in t for x in EXCLUDED_TITLE_TERMS):return False
    return any(re.search(p,t) for p in ALLOWED_TITLE_PATTERNS)

def location_is_us(location):
    """Allow US jobs and US-remote jobs; reject clearly foreign locations.

    Unknown/unstated locations are not rejected here because some ATS feeds omit
    location metadata even when the full posting is US-based.
    """
    raw=(location or "").strip()
    if not raw:return True
    loc=_clean(raw)
    if any(marker in loc for marker in US_MARKERS):return True
    if US_STATE_RE.search(raw):return True
    if any(marker in loc for marker in NON_US_MARKERS):return False
    # A bare Remote is ambiguous; keep it for JD analysis rather than incorrectly
    # discarding a US-eligible remote role.
    if loc in {"remote","remote - remote","multiple locations"}:return True
    return True

def passes_hard_filters(job:dict,profile:dict):
    title=_clean(job.get("title"));reasons=[]
    if not title_is_target(title):reasons.append("title outside strict data-engineering job family")
    if not location_is_us(job.get("location")):reasons.append(f"non-US location: {job.get('location')}")
    eligibility=two_category_filter(job,profile)
    if not eligibility["experience"]["eligible"]:reasons.append(f"experience requirement not met: {eligibility['experience']['required_years']} years required")
    if eligibility["sponsorship"]["eligible"] is False:reasons.append("future H-1B sponsorship unavailable")
    return len(reasons)==0,reasons
