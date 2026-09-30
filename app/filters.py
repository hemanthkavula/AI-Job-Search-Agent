from __future__ import annotations
import re
from app.eligibility import two_category_filter

# Target-title vocabulary is intentionally recall-first. Long/specialized titles are
# accepted when their title itself clearly describes data engineering/platform work.
DIRECT_TARGET_TITLE_PATTERNS=(
 r"\bdata engineer(?:ing)?\b", r"\banalytics engineer(?:ing)?\b",
 r"\bdata platform engineer(?:ing)?\b", r"\bdata infrastructure engineer(?:ing)?\b",
 r"\bdata pipeline engineer(?:ing)?\b", r"\bdata warehouse engineer(?:ing)?\b",
 r"\bdata integration engineer(?:ing)?\b", r"\bdata systems? engineer(?:ing)?\b",
 r"\bdata lake(?:house)? engineer(?:ing)?\b", r"\bdata reliability engineer(?:ing)?\b",
 r"\bdata operations? engineer(?:ing)?\b", r"\bdata ops engineer(?:ing)?\b",
 r"\bdata quality engineer(?:ing)?\b", r"\bdata ingestion engineer(?:ing)?\b",
 r"\bdata transformation engineer(?:ing)?\b", r"\bdata processing engineer(?:ing)?\b",
 r"\bdata streaming engineer(?:ing)?\b", r"\bstreaming data engineer(?:ing)?\b",
 r"\bbig data engineer(?:ing)?\b", r"\bcloud data engineer(?:ing)?\b",
 r"\betl engineer(?:ing)?\b", r"\belt engineer(?:ing)?\b",
 r"\bspark engineer(?:ing)?\b", r"\bpyspark engineer(?:ing)?\b",
 r"\bdatabricks engineer(?:ing)?\b", r"\bsnowflake engineer(?:ing)?\b",
 r"\bwarehouse engineer(?:ing)?\b", r"\bpipeline engineer(?:ing)?\b",
)
# Terms that identify clearly different role families. They are evaluated only when
# the title did not already match an explicit DE-family phrase above.
EXCLUDED_TITLE_TERMS={
 "data analyst","business analyst","data scientist","research scientist","frontend","front end","qa engineer","business intelligence","power bi developer","tableau developer",
 "machine learning engineer","ml engineer","devops engineer","site reliability","database administrator","data architect","solutions architect",
 "product manager","program manager","account executive","solutions engineer","solution engineer","sales engineer","customer engineer","consulting engineer",
 "solutions consultant","solution consultant","technical account manager","customer success","full-stack","full stack","dot net",".net","java developer","siem",
 "security data engineer","marketing technology developer","data governance lead","summer internship","internship","career accelerator program"
}
US_MARKERS={"united states","united states of america","usa","u.s.","u.s.a.","us remote","remote - us","remote, us","remote us"}
US_STATE_NAMES={"alabama","alaska","arizona","arkansas","california","colorado","connecticut","delaware","florida","georgia","hawaii","idaho","illinois","indiana","iowa","kansas","kentucky","louisiana","maine","maryland","massachusetts","michigan","minnesota","mississippi","missouri","montana","nebraska","nevada","new hampshire","new jersey","new mexico","new york","north carolina","north dakota","ohio","oklahoma","oregon","pennsylvania","rhode island","south carolina","south dakota","tennessee","texas","utah","vermont","virginia","washington","west virginia","wisconsin","wyoming","district of columbia"}
NON_US_MARKERS={"romania","bucharest","canada","toronto","vancouver","india","bangalore","bengaluru","hyderabad","pune","chennai","mumbai","delhi","united kingdom","london","ireland","dublin","germany","berlin","munich","france","paris","spain","madrid","netherlands","amsterdam","poland","warsaw","portugal","lisbon","italy","milan","australia","sydney","melbourne","singapore","japan","tokyo","mexico","brazil"}
US_CITY_MARKERS={"san francisco","san jose","seattle","new york","jersey city","glassboro","philadelphia","austin","dallas","houston","chicago","boston","atlanta","charlotte","raleigh","denver","phoenix","los angeles","san diego","portland","miami","tampa","orlando","minneapolis","columbus","cleveland","detroit","pittsburgh","princeton","newark","malvern","plano","redmond","washington dc","washington, dc"}
US_STATE_RE=re.compile(r"(?:^|[,|\s])(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)(?:\s|,|\||$)",re.I)
EMPLOYMENT_ACCEPT_MARKERS=("full-time","full time","fulltime","regular","permanent","employee","w2","w-2")
EMPLOYMENT_REJECT_PATTERNS=(r"\bc2c\b",r"\bcorp[- ]to[- ]corp\b",r"\b1099\b",r"\bpart[- ]time\b",r"\bintern(?:ship)?\b",r"\btemporary\b",r"\btemp\b",r"\bseasonal\b",r"\bvolunteer\b",r"\bcontract[- ]to[- ]hire\b",r"\b(?:employment type|job type|position type)\s*:?\s*(?:w-?2\s+)?contract\b",r"\bcontract duration\s*:",r"\b\d+\s*(?:month|months|mo)\s+contract\b",r"\bcontract position\b",r"\bon a contract basis\b")
CONTRACT_MARKERS=("contract","contractor")
CLEARANCE_PATTERNS=(r"\bts\/sci\b",r"\btop secret\b",r"\bsecret clearance\b",r"\bactive clearance\b",r"\bsecurity clearance required\b",r"\bmust (?:be|hold|possess|have) (?:a )?(?:u\.?s\.? )?security clearance\b",r"\bcleared (?:senior )?data engineer\b")
CITIZENSHIP_PATTERNS=(r"\bu\.?s\.? citizens? only\b",r"\bus citizens? only\b",r"\bmust be (?:a )?u\.?s\.? citizens?\b",r"\bmust be (?:a )?us citizens?\b",r"\bu\.?s\.? citizenship required\b",r"\bus citizenship required\b")
EXCLUDED_EMPLOYER_ALIASES={"fidelity investments","fidelity","fidelity investments inc","fidelity investments institutional services","cigna healthcare","cigna","the cigna group","cigna group","target corporation","target corp","target"}

def employer_is_excluded(company):
    normalized=re.sub(r"[^a-z0-9]+"," ",(company or "").lower()).strip();return bool(normalized) and normalized in EXCLUDED_EMPLOYER_ALIASES

def _clean(v):return re.sub(r"\s+"," ",(v or "").lower()).strip()
def _title_for_match(title):
    t=_clean(title);t=re.sub(r"\s*\((?:remote|hybrid|on[- ]?site|onsite)(?:[^)]*)\)\s*$","",t);return t.strip()
DATA_ENGINEERING_JD_SIGNALS=("data pipeline","data pipelines","etl","elt","data warehouse","data lake","lakehouse","spark","pyspark","databricks","snowflake","bigquery","redshift","airflow","dbt","kafka","data modeling","data ingestion","data transformation","data integration","batch processing","stream processing","distributed data","data platform","data infrastructure")

def jd_is_data_engineering(description):
    text=_clean(description);hits={signal for signal in DATA_ENGINEERING_JD_SIGNALS if signal in text};return len(hits)>=2

def title_is_target(title,description=""):
    t=_title_for_match(title)
    if not t:return False
    # Any long/specialized title containing an explicit DE-family phrase qualifies.
    # Examples: "Staff Research Data Engineering - Platform", "Senior Data Engineer,
    # Risk & Research", "Principal Cloud Data Platform Engineering".
    if any(re.search(p,t,re.I) for p in DIRECT_TARGET_TITLE_PATTERNS):return True
    # Also accept titles where data/research/analytics/platform/infrastructure/pipeline
    # wording and engineering are separated by modifiers, e.g. "Research Data & ML
    # Platform Engineering" or "Data Products and Analytics Engineering". The JD
    # must carry independent DE evidence for these looser constructions.
    has_engineering=bool(re.search(r"\bengineer(?:ing)?\b",t,re.I))
    has_data_context=any(x in t for x in ("data","analytics","warehouse","pipeline","etl","elt","lakehouse","platform","infrastructure","research data","data products"))
    if has_engineering and has_data_context:
        if any(x in t for x in EXCLUDED_TITLE_TERMS):return False
        return jd_is_data_engineering(description)
    if any(x in t for x in EXCLUDED_TITLE_TERMS):return False
    return False

def _description_has_us_location(description):
    text=_clean(description)
    if any(marker in text for marker in US_MARKERS):return True
    if US_STATE_RE.search(description or ""):return True
    if any(re.search(rf"\b{re.escape(state)}\b",text) for state in US_STATE_NAMES):return True
    if any(re.search(rf"\b{re.escape(city)}\b",text) for city in US_CITY_MARKERS):return True
    return False

def _description_has_non_us_location(description):return any(marker in _clean(description) for marker in NON_US_MARKERS)
def location_is_us(location,source=None,description=""):
    raw=(location or "").strip()
    if not raw:
        if _description_has_non_us_location(description):return False
        return True
    loc=_clean(raw)
    if any(marker in loc for marker in US_MARKERS):return True
    if US_STATE_RE.search(raw):return True
    parts={p.strip() for p in re.split(r"[|,/]",loc) if p.strip()}
    if any(city in parts for city in US_CITY_MARKERS):return True
    if any(re.search(rf"\b{re.escape(state)}\b",loc) for state in US_STATE_NAMES):return True
    if any(marker in loc for marker in NON_US_MARKERS):return False
    if loc in {"remote","remote - remote","multiple locations"}:return not _description_has_non_us_location(description)
    return False

def employment_is_target(employment_type, description=""):
    employment=_clean(employment_type);text=_clean(f"{employment_type or ''} {description or ''}")
    if any(re.search(pattern,text) for pattern in EMPLOYMENT_REJECT_PATTERNS):return False
    if any(marker in employment for marker in CONTRACT_MARKERS):return False
    if re.search(r"\bw-?2\b",text):return True
    if any(marker in employment for marker in EMPLOYMENT_ACCEPT_MARKERS):return True
    if any(marker in text for marker in ("full-time","full time","fulltime","regular employee","permanent position")):return True
    return True

def work_authorization_restriction(description="",title=""):
    text=_clean(f"{title or ''} {description or ''}")
    if any(re.search(p,text) for p in CLEARANCE_PATTERNS):return "security clearance requirement"
    if any(re.search(p,text) for p in CITIZENSHIP_PATTERNS):return "US citizenship requirement"
    return None

def passes_hard_filters(job:dict,profile:dict):
    reasons=[]
    if employer_is_excluded(job.get("company") or job.get("company_key")):reasons.append("excluded prior employer")
    if not title_is_target(job.get("title"),job.get("description")):reasons.append("title/JD outside data-engineering job family")
    if not location_is_us(job.get("location"),job.get("source"),job.get("description")):reasons.append("location outside United States target")
    if not employment_is_target(job.get("employment_type"),job.get("description")):reasons.append("employment type outside Full-Time/W-2 target")
    eligibility=two_category_filter(job,profile)
    if not eligibility["experience"]["eligible"]:reasons.append(f"experience requirement not met: {eligibility['experience']['required_years']} years required")
    if eligibility["sponsorship"]["eligible"] is False:reasons.append("future H-1B sponsorship unavailable")
    if eligibility.get("citizenship",{}).get("eligible") is False:reasons.append("US citizenship required")
    if eligibility.get("clearance",{}).get("eligible") is False:reasons.append("security/public-trust clearance required")
    return len(reasons)==0,reasons
