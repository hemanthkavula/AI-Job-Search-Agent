from __future__ import annotations
import re
from app.eligibility import two_category_filter

ALLOWED_TITLE_PATTERNS=[
 r"\bdata engineer(?:ing)?\b",
 r"\bdata platform engineer\b", r"\bdata infrastructure engineer\b",
 r"\bdata pipeline engineer\b", r"\bdata warehouse engineer\b",
 r"\betl engineer\b", r"\bbig data engineer\b",
]
EXCLUDED_TITLE_TERMS={
 "analyst","scientist","frontend","front end","qa engineer","business intelligence","power bi developer","tableau developer",
 "software engineer","machine learning engineer","devops engineer","site reliability","database administrator","data architect","solutions architect",
 "product manager","full-stack","full stack","dot net",".net","java developer","siem","security data engineer","marketing technology developer",
 "data governance lead","summer internship","internship","career accelerator program","junior data engineer"
}

US_MARKERS={"united states","united states of america","usa","u.s.","u.s.a.","us remote","remote - us","remote, us","remote us"}
US_STATE_NAMES={
 "alabama","alaska","arizona","arkansas","california","colorado","connecticut","delaware","florida","georgia","hawaii","idaho","illinois","indiana","iowa","kansas","kentucky","louisiana","maine","maryland","massachusetts","michigan","minnesota","mississippi","missouri","montana","nebraska","nevada","new hampshire","new jersey","new mexico","new york","north carolina","north dakota","ohio","oklahoma","oregon","pennsylvania","rhode island","south carolina","south dakota","tennessee","texas","utah","vermont","virginia","washington","west virginia","wisconsin","wyoming","district of columbia"
}
NON_US_MARKERS={
 "romania","bucharest","canada","toronto","vancouver","india","bangalore","bengaluru","hyderabad","pune","chennai","mumbai","delhi",
 "united kingdom","london","ireland","dublin","germany","berlin","munich","france","paris","spain","madrid","netherlands","amsterdam",
 "poland","warsaw","portugal","lisbon","italy","milan","australia","sydney","melbourne","singapore","japan","tokyo","mexico","brazil"
}
US_CITY_MARKERS={
 "san francisco","san jose","seattle","new york","jersey city","glassboro","philadelphia","austin","dallas","houston",
 "chicago","boston","atlanta","charlotte","raleigh","denver","phoenix","los angeles","san diego","portland","miami",
 "tampa","orlando","minneapolis","columbus","cleveland","detroit","pittsburgh","princeton","newark","malvern","plano",
 "redmond","washington dc","washington, dc"
}
US_STATE_RE=re.compile(r"(?:^|[,|\s])(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)(?:\s|,|\||$)",re.I)

EMPLOYMENT_ACCEPT_MARKERS=("full-time","full time","fulltime","regular","permanent","employee","w2","w-2")
EMPLOYMENT_REJECT_PATTERNS=(r"\bc2c\b",r"\bcorp[- ]to[- ]corp\b",r"\b1099\b",r"\bpart[- ]time\b",r"\bintern(?:ship)?\b",r"\btemporary\b",r"\btemp\b",r"\bseasonal\b",r"\bvolunteer\b")
CONTRACT_MARKERS=("contract","contractor")
CLEARANCE_PATTERNS=(r"\bts\/sci\b",r"\btop secret\b",r"\bsecret clearance\b",r"\bactive clearance\b",r"\bsecurity clearance required\b",r"\bmust (?:be|hold|possess|have) (?:a )?(?:u\.?s\.? )?security clearance\b",r"\bcleared (?:senior )?data engineer\b")
CITIZENSHIP_PATTERNS=(r"\bu\.?s\.? citizens? only\b",r"\bus citizens? only\b",r"\bmust be (?:a )?u\.?s\.? citizens?\b",r"\bmust be (?:a )?us citizens?\b",r"\bu\.?s\.? citizenship required\b",r"\bus citizenship required\b")

def _clean(v):return re.sub(r"\s+"," ",(v or "").lower()).strip()
def _title_for_match(title):
    # Parenthetical work-arrangement/location qualifiers do not change the role family.
    t=_clean(title)
    t=re.sub(r"\s*\((?:remote|hybrid|on[- ]?site|onsite)(?:[^)]*)\)\s*$","",t)
    return t.strip()
DATA_ENGINEERING_JD_SIGNALS=(
 "data pipeline","data pipelines","etl","elt","data warehouse","data lake","lakehouse","spark","pyspark","databricks","snowflake","bigquery","redshift","airflow","dbt","kafka","data modeling","data ingestion","data transformation","data integration"
)

def jd_is_data_engineering(description):
    text=_clean(description)
    # Require several independent DE signals for adjacent titles so a single generic
    # technology mention does not turn an unrelated role into a Data Engineering job.
    hits={signal for signal in DATA_ENGINEERING_JD_SIGNALS if signal in text}
    return len(hits)>=3

def title_is_target(title,description=""):
    t=_title_for_match(title)
    # User's governing title rule: if the title contains the phrase "data engineer"
    # anywhere as words, it belongs to the target family. Prefixes/suffixes and
    # specializations do not disqualify it (e.g. Senior Data Engineer - Airflow,
    # AWS Data Engineer, Data Engineer II, Lead Data Engineer / Snowflake).
    if re.search(r"\bdata engineer(?:ing)?\b",t,re.I):return True
    # Keep a small adjacent DE-family set for titles that do not literally contain
    # "data engineer", such as Data Platform Engineer.
    if any(x in t for x in EXCLUDED_TITLE_TERMS):return False
    if any(re.search(p,t,re.I) for p in ALLOWED_TITLE_PATTERNS[1:]):return True
    # Adjacent data roles can qualify from their responsibilities even when the title
    # does not literally say Data Engineer (e.g. Data Analytics Engineer / Data Integration Engineer).
    return jd_is_data_engineering(description)

def _description_has_non_us_location(description):
    text=_clean(description)
    # Discovery providers can occasionally return an empty/incorrect location even
    # when the JD excerpt explicitly identifies a foreign office. Treat explicit
    # foreign country/city evidence in the posting as authoritative.
    return any(marker in text for marker in NON_US_MARKERS)

def location_is_us(location,source=None,description=""):
    raw=(location or "").strip();src=_clean(source)
    if not raw:
        if _description_has_non_us_location(description):return False
        return src=="dice"
    loc=_clean(raw)
    if any(marker in loc for marker in US_MARKERS):return True
    if US_STATE_RE.search(raw):return True
    # Some ATS providers return only a US city (e.g. "San Francisco") without
    # state/country. Accept known unambiguous US city names instead of rejecting them.
    parts={p.strip() for p in re.split(r"[|,/]",loc) if p.strip()}
    if any(city in parts for city in US_CITY_MARKERS):return True
    if any(re.search(rf"\b{re.escape(state)}\b",loc) for state in US_STATE_NAMES):return True
    if any(marker in loc for marker in NON_US_MARKERS):return False
    if loc in {"remote","remote - remote","multiple locations"}:return src=="dice"
    return False

def employment_is_target(employment_type, description=""):
    employment=_clean(employment_type);text=_clean(f"{employment_type or ''} {description or ''}")
    if any(re.search(pattern,text) for pattern in EMPLOYMENT_REJECT_PATTERNS):return False
    if re.search(r"\bw-?2\b",text):return True
    if any(marker in employment for marker in EMPLOYMENT_ACCEPT_MARKERS):return True
    if any(marker in employment for marker in CONTRACT_MARKERS):return False
    if any(marker in text for marker in ("full-time","full time","fulltime","regular employee","permanent position")):return True
    return not employment

def work_authorization_restriction(description="",title=""):
    text=_clean(f"{title or ''} {description or ''}")
    if any(re.search(p,text) for p in CLEARANCE_PATTERNS):return "security clearance requirement"
    if any(re.search(p,text) for p in CITIZENSHIP_PATTERNS):return "US citizenship requirement"
    return None

def passes_hard_filters(job:dict,profile:dict):
    """Apply only the three governing eligibility criteria.

    1) Data Engineering family (title, or adjacent title supported by JD evidence)
    2) Full-time/W-2 employment target
    3) Future sponsorship must not be explicitly unavailable
    4) Experience requirement must fit the configured target window

    Location, citizenship and clearance remain metadata for later application
    handling; employment type is a hard gate because the configured search targets
    Full-Time/W-2 roles.
    """
    reasons=[]
    if not title_is_target(job.get("title"),job.get("description")):
        reasons.append("title/JD outside data-engineering job family")
    if not employment_is_target(job.get("employment_type"),job.get("description")):
        reasons.append("employment type outside Full-Time/W-2 target")
    eligibility=two_category_filter(job,profile)
    if not eligibility["experience"]["eligible"]:
        reasons.append(f"experience requirement not met: {eligibility['experience']['required_years']} years required")
    if eligibility["sponsorship"]["eligible"] is False:
        reasons.append("future H-1B sponsorship unavailable")
    if eligibility.get("citizenship",{}).get("eligible") is False:
        reasons.append("US citizenship required")
    if eligibility.get("clearance",{}).get("eligible") is False:
        reasons.append("security/public-trust clearance required")
    return len(reasons)==0,reasons
