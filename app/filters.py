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

EMPLOYMENT_ACCEPT_MARKERS=("full-time","full time","fulltime","regular","permanent","employee","w2","w-2")
EMPLOYMENT_REJECT_PATTERNS=(
 r"\bc2c\b",r"\bcorp[- ]to[- ]corp\b",r"\b1099\b",r"\bpart[- ]time\b",
 r"\bintern(?:ship)?\b",r"\btemporary\b",r"\btemp\b",r"\bseasonal\b",r"\bvolunteer\b"
)
CONTRACT_MARKERS=("contract","contractor","consulting","consultant")

def _clean(v):return re.sub(r"\s+"," ",(v or "").lower()).strip()
def title_is_target(title):
    t=_clean(title)
    if any(x in t for x in EXCLUDED_TITLE_TERMS):return False
    return any(re.search(p,t) for p in ALLOWED_TITLE_PATTERNS)

def location_is_us(location):
    """Allow US jobs and US-remote jobs; reject clearly foreign locations."""
    raw=(location or "").strip()
    if not raw:return True
    loc=_clean(raw)
    if any(marker in loc for marker in US_MARKERS):return True
    if US_STATE_RE.search(raw):return True
    if any(marker in loc for marker in NON_US_MARKERS):return False
    if loc in {"remote","remote - remote","multiple locations"}:return True
    return True

def employment_is_target(employment_type, description=""):
    """Allow full-time employment or W-2 contracting only.

    Reject markers use word boundaries so ordinary JD words such as "internal" or
    "international" cannot be mistaken for "intern". Explicit internship/temporary/
    C2C/1099 language still blocks the role.
    """
    employment=_clean(employment_type)
    text=_clean(f"{employment_type or ''} {description or ''}")
    if any(re.search(pattern,text) for pattern in EMPLOYMENT_REJECT_PATTERNS):return False
    if re.search(r"\bw-?2\b",text):return True
    if any(marker in employment for marker in EMPLOYMENT_ACCEPT_MARKERS):return True
    if any(marker in employment for marker in CONTRACT_MARKERS):return False
    if any(marker in text for marker in ("full-time","full time","fulltime","regular employee","permanent position")):return True
    return True

def passes_hard_filters(job:dict,profile:dict):
    title=_clean(job.get("title"));reasons=[]
    if not title_is_target(title):reasons.append("title outside strict data-engineering job family")
    if not location_is_us(job.get("location")):reasons.append(f"non-US location: {job.get('location')}")
    if not employment_is_target(job.get("employment_type"),job.get("description")):reasons.append(f"employment type outside Full-Time/W2 target: {job.get('employment_type') or 'not explicitly stated'}")
    eligibility=two_category_filter(job,profile)
    if not eligibility["experience"]["eligible"]:reasons.append(f"experience requirement not met: {eligibility['experience']['required_years']} years required")
    if eligibility["sponsorship"]["eligible"] is False:reasons.append("future H-1B sponsorship unavailable")
    return len(reasons)==0,reasons
