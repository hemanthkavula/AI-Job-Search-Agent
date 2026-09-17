from __future__ import annotations
import re
from app.eligibility import two_category_filter

ALLOWED_TITLE_PATTERNS=[
 r"^(?:senior |sr\.? |lead |principal |staff |aws |azure |cloud |big |etl |analytics )?data engineer(?:\s+(?:i|ii|iii|iv|1|2|3|4))?(?:\s*[-–—,:].*)?$",
 r"^(?:senior |sr\.? |lead |principal |staff )?data platform engineer(?:\s*[-–—,:].*)?$",
 r"^(?:senior |sr\.? |lead |principal |staff )?data infrastructure engineer(?:\s*[-–—,:].*)?$",
 r"^(?:senior |sr\.? |lead |principal |staff )?data pipeline engineer(?:\s*[-–—,:].*)?$",
 r"^(?:avp,?\s*)?(?:senior |sr\.? )?data engineer(?:\s*[-–—,:].*)?$",
 r"^engineer\s+(?:i|ii|iii|iv|1|2|3|4)\s*[-–—:]\s*data engineer(?:\s*[-–—,:].*)?$",
]
# Adjacent-specialty titles are intentionally rejected. A JD may still contain Java/.NET/etc.;
# the role title itself must remain fundamentally Data Engineering.
EXCLUDED_TITLE_TERMS={
 "analyst","scientist","frontend","front end","qa engineer","business intelligence","power bi developer","tableau developer",
 "software engineer","machine learning engineer","devops engineer","site reliability","database administrator","data architect","solutions architect",
 "product manager","full-stack","full stack","dot net",".net","java developer","siem","security data engineer","marketing technology developer",
 "data governance lead","summer internship","internship","career accelerator program","junior data engineer"
}

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
CONTRACT_MARKERS=("contract","contractor")
CLEARANCE_PATTERNS=(
 r"\bts\/sci\b",r"\btop secret\b",r"\bsecret clearance\b",r"\bactive clearance\b",r"\bsecurity clearance required\b",
 r"\bmust (?:be|hold|possess|have) (?:a )?(?:u\.?s\.? )?security clearance\b",r"\bcleared (?:senior )?data engineer\b"
)
CITIZENSHIP_PATTERNS=(
 r"\bu\.?s\.? citizens? only\b",r"\bus citizens? only\b",r"\bmust be (?:a )?u\.?s\.? citizens?\b",r"\bmust be (?:a )?us citizens?\b",
 r"\bu\.?s\.? citizenship required\b",r"\bus citizenship required\b"
)

def _clean(v):return re.sub(r"\s+"," ",(v or "").lower()).strip()
def title_is_target(title):
    t=_clean(title)
    if any(x in t for x in EXCLUDED_TITLE_TERMS):return False
    return any(re.search(p,t) for p in ALLOWED_TITLE_PATTERNS)

def location_is_us(location,source=None):
    """Require affirmative US evidence unless the provider search itself is US-scoped."""
    raw=(location or "").strip();src=_clean(source)
    if not raw:
        # Dice discovery is explicitly sent to the provider with location=United States.
        # Keep that provider assertion, but later full-JD hydration must re-check restrictions.
        return src=="dice"
    loc=_clean(raw)
    if any(marker in loc for marker in US_MARKERS):return True
    if US_STATE_RE.search(raw):return True
    if any(marker in loc for marker in NON_US_MARKERS):return False
    if loc in {"remote","remote - remote","multiple locations"}:return src=="dice"
    return False

def employment_is_target(employment_type, description=""):
    employment=_clean(employment_type)
    text=_clean(f"{employment_type or ''} {description or ''}")
    if any(re.search(pattern,text) for pattern in EMPLOYMENT_REJECT_PATTERNS):return False
    if re.search(r"\bw-?2\b",text):return True
    if any(marker in employment for marker in EMPLOYMENT_ACCEPT_MARKERS):return True
    if any(marker in employment for marker in CONTRACT_MARKERS):return False
    if any(marker in text for marker in ("full-time","full time","fulltime","regular employee","permanent position")):return True
    # Unknown employment type is allowed at lightweight discovery only; complete JD is
    # required before resume generation and can supply the final evidence.
    return not employment

def work_authorization_restriction(description="",title=""):
    text=_clean(f"{title or ''} {description or ''}")
    if any(re.search(p,text) for p in CLEARANCE_PATTERNS):return "security clearance requirement"
    if any(re.search(p,text) for p in CITIZENSHIP_PATTERNS):return "US citizenship requirement"
    return None

def passes_hard_filters(job:dict,profile:dict):
    title=_clean(job.get("title"));reasons=[]
    if not title_is_target(title):reasons.append("title outside strict data-engineering job family")
    if not location_is_us(job.get("location"),job.get("source")):reasons.append(f"non-US or unverified US location: {job.get('location') or 'not stated'}")
    if not employment_is_target(job.get("employment_type"),job.get("description")):reasons.append(f"employment type outside Full-Time/W2 target: {job.get('employment_type') or 'not explicitly stated'}")
    restriction=work_authorization_restriction(job.get("description"),job.get("title"))
    if restriction:reasons.append(restriction)
    eligibility=two_category_filter(job,profile)
    if not eligibility["experience"]["eligible"]:reasons.append(f"experience requirement not met: {eligibility['experience']['required_years']} years required")
    if eligibility["sponsorship"]["eligible"] is False:reasons.append("future H-1B sponsorship unavailable")
    return len(reasons)==0,reasons
