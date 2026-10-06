from __future__ import annotations
import json
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
 "product manager","program manager","platform manager","account executive","solutions engineer","solution engineer","sales engineer",
 "customer engineer","consulting engineer","solutions consultant","solution consultant","technical account manager","customer success",
 "full-stack","full stack","dot net",".net","java developer","siem","security data engineer","marketing technology developer",
 "data governance lead","summer internship","internship","career accelerator program","junior data engineer"
}

US_MARKERS={
 "united states","united states of america","usa","u.s.","u.s.a.","us remote","remote - us","remote, us","remote us",
 "remote in the united states","remote within the united states","anywhere in the united states","united states remote",
 "remote in the u.s.","remote within the u.s.","u.s.-based","u.s. based","us-based","us based"
}
US_STATE_NAMES={
 "alabama","alaska","arizona","arkansas","california","colorado","connecticut","delaware","florida","georgia","hawaii","idaho","illinois","indiana","iowa","kansas","kentucky","louisiana","maine","maryland","massachusetts","michigan","minnesota","mississippi","missouri","montana","nebraska","nevada","new hampshire","new jersey","new mexico","new york","north carolina","north dakota","ohio","oklahoma","oregon","pennsylvania","rhode island","south carolina","south dakota","tennessee","texas","utah","vermont","virginia","washington","west virginia","wisconsin","wyoming","district of columbia"
}
NON_US_MARKERS={
 "emea","apac","latam","europe","european union","asia pacific","middle east","africa","australia and new zealand","australia & new zealand","anz",
 "romania","bucharest","canada","toronto","vancouver","india","bangalore","bengaluru","hyderabad","pune","chennai","mumbai","delhi",
 "united kingdom","london","ireland","dublin","germany","berlin","munich","france","paris","spain","madrid","netherlands","amsterdam",
 "poland","warsaw","portugal","lisbon","italy","milan","australia","sydney","melbourne","singapore","japan","tokyo","mexico","brazil"
}
GLOBAL_LOCATION_MARKERS={"global","worldwide","anywhere","international","remote worldwide","remote - global","remote global"}
US_CITY_MARKERS={
 "san francisco","san jose","seattle","new york","jersey city","glassboro","philadelphia","austin","dallas","houston",
 "chicago","boston","atlanta","charlotte","raleigh","denver","phoenix","los angeles","san diego","portland","miami",
 "tampa","orlando","minneapolis","columbus","cleveland","detroit","pittsburgh","princeton","newark","malvern","plano",
 "redmond","washington dc","washington, dc"
}
US_STATE_RE=re.compile(r"(?:^|[,|\s])(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)(?:\s|,|\||$)")

EMPLOYMENT_ACCEPT_MARKERS=("full-time","full time","fulltime","regular","permanent","employee","w2","w-2")
EMPLOYMENT_REJECT_PATTERNS=(r"\bc2c\b",r"\bcorp[- ]to[- ]corp\b",r"\b1099\b",r"\bpart[- ]time\b",r"\bintern(?:ship)?\b",r"\btemporary\b",r"\btemp\b",r"\bseasonal\b",r"\bvolunteer\b",r"\bcontract[- ]to[- ]hire\b",r"\b(?:employment type|job type|position type)\s*:?\s*(?:w-?2\s+)?contract\b",r"\bcontract duration\s*:",r"\b\d+\s*(?:month|months|mo)\s+contract\b",r"\bcontract position\b",r"\bon a contract basis\b")
CONTRACT_MARKERS=("contract","contractor")
CLEARANCE_PATTERNS=(r"\bts\/sci\b",r"\btop secret\b",r"\bsecret clearance\b",r"\bactive clearance\b",r"\bsecurity clearance required\b",r"\bmust (?:be|hold|possess|have) (?:a )?(?:u\.?s\.? )?security clearance\b",r"\bcleared (?:senior )?data engineer\b")
CITIZENSHIP_PATTERNS=(r"\bu\.?s\.? citizens? only\b",r"\bus citizens? only\b",r"\bmust be (?:a )?u\.?s\.? citizens?\b",r"\bmust be (?:a )?us citizens?\b",r"\bu\.?s\.? citizenship required\b",r"\bus citizenship required\b")

EXCLUDED_EMPLOYER_ALIASES={
 "fidelity investments","fidelity","fidelity investments inc","fidelity investments institutional services",
 "cigna healthcare","cigna","the cigna group","cigna group",
 "target corporation","target corp","target"
}

def employer_is_excluded(company):
    normalized=re.sub(r"[^a-z0-9]+"," ",(company or "").lower()).strip()
    if not normalized:return False
    return normalized in EXCLUDED_EMPLOYER_ALIASES

def _clean(v):return re.sub(r"\s+"," ",(v or "").lower()).strip()
def _has_bounded_marker(text,marker):
    return re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])",text) is not None

def _title_for_match(title):
    t=_clean(title)
    t=re.sub(r"\s*\((?:remote|hybrid|on[- ]?site|onsite)(?:[^)]*)\)\s*$","",t)
    return t.strip()
DATA_ENGINEERING_JD_SIGNALS=(
 "data pipeline","data pipelines","etl","elt","data warehouse","data lake","lakehouse","spark","pyspark","databricks","snowflake","bigquery","redshift","airflow","dbt","kafka","data modeling","data ingestion","data transformation","data integration"
)

def jd_is_data_engineering(description):
    text=_clean(description)
    hits={signal for signal in DATA_ENGINEERING_JD_SIGNALS if signal in text}
    return len(hits)>=3

def title_is_target(title,description=""):
    t=_title_for_match(title)
    if re.search(r"\b(manager|director|architect|consultant)\b",t,re.I):return False
    if re.search(r"\bdata engineer(?:ing)?\b",t,re.I):return True
    if re.search(r"\banalytics engineer\b",t,re.I):return jd_is_data_engineering(description)
    if re.search(r"\bsoftware engineer\b",t,re.I) and any(x in t for x in ("data platform","data infrastructure","data pipeline","data warehouse")):
        return jd_is_data_engineering(description)
    if any(x in t for x in EXCLUDED_TITLE_TERMS):return False
    if any(re.search(p,t,re.I) for p in ALLOWED_TITLE_PATTERNS[1:]):return True
    adjacent_engineering_title=("engineer" in t and any(marker in t for marker in ("data","analytics","etl","warehouse","pipeline","integration")))
    return adjacent_engineering_title and jd_is_data_engineering(description)

def _description_has_non_us_location(description):
    text=_clean(description)
    return any(_has_bounded_marker(text,marker) for marker in NON_US_MARKERS)

def _description_has_us_location(description):
    text=_clean(description)
    if not text:return False
    us=r"(?:united states(?: of america)?|u\.?s\.?a?\.?|usa)"
    scoped_patterns=(
        rf"\b(?:job|role|position|work)\s+location\s*(?:is|:|-)?\s*(?:remote\s*[-,:]?\s*)?{us}\b",
        rf"\b(?:this|the)\s+(?:job|role|position)\s+(?:is\s+)?(?:based|located)\s+(?:in|within)\s+(?:the\s+)?{us}\b",
        rf"\b(?:must|should)\s+(?:be\s+)?(?:based|located|reside|live)\s+(?:in|within)\s+(?:the\s+)?{us}\b",
        rf"\b(?:candidates?|applicants?)\s+(?:must\s+)?(?:be\s+)?(?:based|located|residing|living)\s+(?:in|within)\s+(?:the\s+)?{us}\b",
        rf"\bremote(?:\s+(?:job|role|position|opportunity))?\s*(?:[-,:|]\s*|\s+(?:in|within)\s+)(?:the\s+)?{us}\b",
        rf"\b(?:open|available)\s+to\s+(?:candidates?|applicants?)\s+(?:based|located|residing|living)?\s*(?:in|within)?\s*(?:the\s+)?{us}\b",
        rf"\bwork(?:ing)?\s+(?:remotely\s+)?(?:from|in|within)\s+(?:the\s+)?{us}\b",
    )
    if any(re.search(pattern,text,re.I) for pattern in scoped_patterns):return True
    scope_words=r"(?:location|based|located|reside|residing|live|living|office|work from|work in)"
    for state in US_STATE_NAMES:
        if re.search(rf"\b{scope_words}\b.{{0,35}}\b{re.escape(state)}\b",text,re.I):return True
    for city in US_CITY_MARKERS:
        if re.search(rf"\b{scope_words}\b.{{0,35}}\b{re.escape(city)}\b",text,re.I):return True
    return False

def _flatten_application_questions(job:dict) -> str:
    values=[]
    for key in ("application_questions","screening_questions","questions","application_form"):
        value=job.get(key)
        if value in (None,"",[],{}):continue
        if isinstance(value,str):values.append(value)
        else:
            try:values.append(json.dumps(value,ensure_ascii=False))
            except Exception:values.append(str(value))
    return " ".join(values)

def _questions_show_us_scope(text):
    cleaned=_clean(text)
    if not cleaned:return False
    patterns=(
        r"\b(?:are|will) you (?:currently )?(?:based|located|residing|living) (?:in|within) (?:the )?(?:united states|u\.?s\.?a?\.?|usa)\b",
        r"\bdo you (?:currently )?(?:reside|live) (?:in|within) (?:the )?(?:united states|u\.?s\.?a?\.?|usa)\b",
        r"\bthis (?:job|role|position) (?:is )?(?:only )?(?:available|open) (?:in|to candidates in) (?:the )?(?:united states|u\.?s\.?a?\.?|usa)\b",
    )
    return any(re.search(pattern,cleaned,re.I) for pattern in patterns)

def location_is_us(location,source=None,description="",application_questions=""):
    """Require positive vacancy-level evidence that the opening is U.S.-based.

    Source labels can be coarse or stale. For foreign/regional/global/ambiguous
    labels, inspect the full JD and ATS application questions. Explicit U.S.
    vacancy evidence may resolve a conflicting source label; generic mentions of
    U.S. offices, teams, customers, or company nationality do not count.
    """
    raw=(location or "").strip()
    loc=_clean(raw)
    richer_us_evidence=_description_has_us_location(description) or _questions_show_us_scope(application_questions)

    if raw:
        explicit_us_marker=any(marker in loc for marker in US_MARKERS)
        parts={p.strip() for p in re.split(r"[|,/]",loc) if p.strip()}
        explicit_us_city=any(city in parts for city in US_CITY_MARKERS)
        explicit_us_state_name=any(re.search(rf"\b{re.escape(state)}\b",loc) for state in US_STATE_NAMES)
        has_foreign_marker=any(_has_bounded_marker(loc,marker) for marker in NON_US_MARKERS)
        has_global_marker=any(_has_bounded_marker(loc,marker) for marker in GLOBAL_LOCATION_MARKERS)

        # Foreign/global evidence must be resolved before checking two-letter U.S.
        # state abbreviations, because country codes such as IN can otherwise be
        # misread as Indiana. A genuinely mixed label containing explicit U.S.
        # wording/city/state-name can still pass.
        if has_foreign_marker or has_global_marker:
            if explicit_us_marker or explicit_us_city or explicit_us_state_name:return True
            return richer_us_evidence

        if explicit_us_marker:return True
        if US_STATE_RE.search(raw):return True
        if explicit_us_city:return True
        if explicit_us_state_name:return True

        if loc in {"remote","remote - remote","multiple locations","various locations"} or loc.startswith("remote "):
            return richer_us_evidence
        return richer_us_evidence

    return richer_us_evidence

def employment_is_target(employment_type, description=""):
    employment=_clean(employment_type);text=_clean(f"{employment_type or ''} {description or ''}")
    if any(re.search(pattern,text) for pattern in EMPLOYMENT_REJECT_PATTERNS):return False
    if any(marker in employment for marker in CONTRACT_MARKERS):return False
    if re.search(r"\bw-?2\b",text):return True
    if any(marker in employment for marker in EMPLOYMENT_ACCEPT_MARKERS):return True
    if any(marker in employment for marker in CONTRACT_MARKERS):return False
    if any(marker in text for marker in ("full-time","full time","fulltime","regular employee","permanent position")):return True
    return True

def work_authorization_restriction(description="",title=""):
    text=_clean(f"{title or ''} {description or ''}")
    if any(re.search(p,text) for p in CLEARANCE_PATTERNS):return "security clearance requirement"
    if any(re.search(p,text) for p in CITIZENSHIP_PATTERNS):return "US citizenship requirement"
    return None

def passes_hard_filters(job:dict,profile:dict):
    reasons=[]
    if employer_is_excluded(job.get("company") or job.get("company_key")):
        reasons.append("excluded prior employer")
    if not title_is_target(job.get("title"),job.get("description")):
        reasons.append("title/JD outside data-engineering job family")
    application_questions=_flatten_application_questions(job)
    if not location_is_us(job.get("location"),job.get("source"),job.get("description"),application_questions):
        reasons.append("location outside United States target")
    if not employment_is_target(job.get("employment_type"),job.get("description")):
        reasons.append("employment type outside Full-Time/W-2 target")
    eligibility=two_category_filter(job,profile)
    if not eligibility["experience"]["eligible"]:
        reasons.append(f"experience requirement not met: {eligibility['experience']['required_years']} years required")
    if eligibility.get("citizenship",{}).get("eligible") is False:
        reasons.append("US citizenship required")
    if eligibility.get("clearance",{}).get("eligible") is False:
        reasons.append("security/public-trust clearance required")
    return len(reasons)==0,reasons
