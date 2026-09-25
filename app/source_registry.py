from __future__ import annotations
import json,re
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_PATH=Path("generated/discovered_sources.json")
PATTERNS={
 "greenhouse":[r"(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)",r"boards\.greenhouse\.io/([^/?#]+)"],
 "lever":[r"jobs\.lever\.co/([^/?#]+)"],
 "ashby":[r"jobs\.ashbyhq\.com/([^/?#]+)"],
 "smartrecruiters":[r"(?:jobs\.)?smartrecruiters\.com/([^/?#]+)"],
 "workday":[
   r"https?://([^.]+)\.wd\d+\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/?#]+)",
   r"https?://([^.]+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/?#]+)",
 ],
 "icims":[
   r"https?://(?:careers-)?([^.]+)\.icims\.com/",
 ],
 "jobvite":[
   r"https?://jobs\.jobvite\.com/([^/?#]+)",
   r"https?://([^.]+)\.jobvite\.com/",
 ],
 "dayforce":[
   r"https?://jobs\.dayforcehcm\.com/[^/?#]+/([^/?#]+)",
   r"https?://([^.]+)\.dayforcehcm\.com/",
 ],
 "ultipro":[
   r"https?://recruiting(?:\d+)?\.ultipro\.com/([^/?#]+)",
   r"https?://([^.]+)\.ultipro\.com/",
 ],
 "recruiting_com":[
   r"https?://jobs\.recruiting\.com/([^/?#]+)",
   r"https?://([^.]+)\.recruiting\.com/",
 ],
 "adp_workforce_now":[
   r"https?://workforcenow\.adp\.com/mascsr/default/mdf/recruitment/recruitment\.html\?cid=([^&#]+)",
   r"https?://jobs\.adp\.com/([^/?#]+)",
 ],
 "workable":[r"https?://apply\.workable\.com/([^/?#]+)",r"https?://jobs\.workable\.com/([^/?#]+)"],
 "recruitee":[r"https?://([^.]+)\.recruitee\.com/",r"https?://careers\.recruitee\.com/([^/?#]+)"],
 "teamtailor":[r"https?://([^.]+)\.teamtailor\.com/"],
 "bamboohr":[r"https?://([^.]+)\.bamboohr\.com/careers"],
 "phenom":[r"https?://([^/]+)/(?:us/)?en/(?:careers|jobs)",r"https?://([^/]*phenom[^/]*)/"],
 "avature":[r"https?://([^.]+)\.avature\.net/"],
 "taleo":[r"https?://[^/]*taleo\.net/[^?]*\?(?:[^#]*&)?org=([^&#]+)",r"https?://([^.]+)\.taleo\.net/"],
 "cornerstone":[r"https?://([^.]+)\.csod\.com/"],
 "jazzhr":[r"https?://([^.]+)\.applytojob\.com/"],
 "breezyhr":[r"https?://([^.]+)\.breezy\.hr/"],
 "paylocity":[r"https?://recruiting\.paylocity\.com/recruiting/jobs/[^/]+/([^/?#]+)"],
 "rippling":[r"https?://ats\.rippling\.com/([^/?#]+)"],
 "pinpoint":[r"https?://([^.]+)\.pinpointhq\.com/"],
 "brassring":[r"https?://[^/]*brassring\.com/"],
 "careerplug":[r"https?://([^.]+)\.careerplug\.com/"],
 "freshteam":[r"https?://([^.]+)\.freshteam\.com/jobs"],
 "jobscore":[r"https?://careers\.jobscore\.com/careers/([^/?#]+)"],
 "personio":[r"https?://([^.]+)\\.jobs\\.personio\\.(?:de|com)/"],
 "eightfold":[r"https?://([^.]+)\\.eightfold\\.ai/"],
 "successfactors":[r"https?://[^/]*(?:successfactors|successfactors\\.eu|successfactors\\.com)/",r"https?://career[^/]*\\.successfactors\\."],
 "oracle":[r"https?://[^/]*oraclecloud\\.com/hcmUI/CandidateExperience/",r"https?://[^/]*oraclecloud\\.com/.*CandidateExperience/"],
 "ukg":[r"https?://[^/]*\\.rec\\.pro\\.ukg\\.net/",r"https?://recruiting\\.ultipro\\.com/"],
 "paycom":[r"https?://www\\.paycomonline\\.net/v4/ats/web\\.php/",r"https?://www\\.paycomonline\\.net/v4/ats/"],
 "bullhorn":[r"https?://[^/]*bullhornstaffing\\.com/",r"https?://public\\.bullhornstaffing\\.com/"],
 "comeet":[r"https?://www\\.comeet\\.com/jobs/([^/?#]+)",r"https?://jobs\\.comeet\\.com/"],
 "clearcompany":[r"https?://[^/]*clearcompany\\.com/",r"https?://careers\\.clearcompany\\.com/"],
 "applicantpro":[r"https?://[^/]*\\.applicantpro\\.com/jobs/"],
 "fountain":[r"https?://[^/]*fountain\\.com/jobs/",r"https?://apply\\.fountain\\.com/"],
 "hirebridge":[r"https?://[^/]*hirebridge\\.com/"],
 "jobdiva":[r"https?://[^/]*jobdiva\\.com/"],
 "zoho_recruit":[r"https?://jobs\\.zohorecruit\\.(?:com|eu|in)/",r"https?://[^/]*zohorecruit\\.(?:com|eu|in)/jobs/"],
 "manatal":[r"https?://[^/]*manatal\\.com/jobs/"],
 "join":[r"https?://join\\.com/companies/([^/?#]+)"],
 "greenhouse_eu":[r"https?://job-boards\\.eu\\.greenhouse\\.io/([^/?#]+)"],
 "applitrack":[r"https?://[^/]*applitrack\\.com/",r"https?://[^/]*frontlineeducation\\.com/"],
 "hireology":[r"https?://[^/]*hireology\\.com/"],
 "paycor":[r"https?://[^/]*paycor\\.com/"],
 "peopleadmin":[r"https?://[^/]*peopleadmin\\.com/"],
 "isolved":[r"https?://[^/]*isolvedhire\\.com/",r"https?://[^/]*isolved\\.com/"],
 "hibob":[r"https?://[^/]*hibob\\.com/jobs/",r"https?://jobs\\.hibob\\.com/"],
 "gohire":[r"https?://[^/]*gohire\\.io/"],
 "hiringthing":[r"https?://[^/]*hiringthing\\.com/"],
 "homerun":[r"https?://[^/]*homerun\\.co/"],
 "pageup":[r"https?://[^/]*pageuppeople\\.com/",r"https?://[^/]*pageuppeople\\.com/cw/"],
 "trinet":[r"https?://[^/]*trinet\\.com/"],
 "dover":[r"https?://[^/]*dover\\.com/jobs/",r"https?://app\\.dover\\.com/"],
 "gem":[r"https?://jobs\\.gem\\.com/([^/?#]+)"],
 "polymer":[r"https?://jobs\\.polymer\\.co/([^/?#]+)"],
 "hirehive":[r"https?://[^/]*hirehive\\.com/"],
 "kula":[r"https?://jobs\\.kula\\.ai/",r"https?://[^/]*kula\\.ai/jobs/"],
 "rival":[r"https?://[^/]*rival-hr\\.com/",r"https?://[^/]*rival\\.com/jobs/"],
 "werecruit":[r"https?://[^/]*werecruit\\.io/",r"https?://[^/]*werecruit\\.com/"],
 "deel":[r"https?://jobs\\.deel\\.com/",r"https?://[^/]*deel\\.com/jobs/"],
 "firststage":[r"https?://[^/]*firststage\\.co/"],
 "recruiterbox":[r"https?://[^/]*recruiterbox\\.com/"],
 "talentbrew":[r"https?://[^/]*talentbrew\\.com/"],
 "radancy":[r"https?://[^/]*radancy\\.com/"],
 "paradox":[r"https?://[^/]*paradox\\.ai/"],
 "applicantstack":[r"https?://[^/]*applicantstack\\.com/",r"https?://[^/]*applicantstack\\.com/x/"],
 "jazzhr_alt":[r"https?://[^/]*jazzhr\\.com/"],
 "ceipal":[r"https?://[^/]*ceipal\\.com/"],
 "trakstar_hire":[r"https?://[^/]*hire\\.trakstar\\.com/"],
 "neogov":[r"https?://[^/]*governmentjobs\\.com/",r"https?://[^/]*neogov\\.com/"],
 "schooljobs":[r"https?://[^/]*schooljobs\\.com/"],
 "higheredjobs":[r"https?://[^/]*higheredjobs\\.com/"],
 "applynow":[r"https?://[^/]*applynow\\.net/"],
 "talentreef":[r"https?://[^/]*talentreef\\.com/"],
 "icims_alt":[r"https?://[^/]*icims\\.com/jobs/"],
 "jobappnetwork":[r"https?://[^/]*jobappnetwork\\.com/"],
 "myworkchoice":[r"https?://[^/]*myworkchoice\\.com/"],
 "ultipro_ukg":[r"https?://[^/]*ultipro\\.com/"],
}

def load_registry(path=DEFAULT_PATH):
 p=Path(path)
 if not p.exists():return {k:[] for k in PATTERNS}
 try:return json.loads(p.read_text(encoding="utf-8"))
 except Exception:return {k:[] for k in PATTERNS}

def save_registry(registry,path=DEFAULT_PATH):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(registry,indent=2),encoding="utf-8")

def detect_ats(url):
 if not url:return None,None
 parsed=urlparse(url)
 for provider,patterns in PATTERNS.items():
  for pat in patterns:
   m=re.search(pat,url,re.I)
   if not m:continue
   groups=[x for x in m.groups() if x]
   if provider=="workday" and groups:return provider,"|".join(groups)
   if groups:return provider,groups[0]
   # Host-only ATS patterns still need a stable reusable identity so they can
   # be learned instead of silently discarded.
   host=(parsed.netloc or "").lower()
   path=(parsed.path or "").strip("/")
   identifier=host
   if provider=="adp_workforce_now":
    from urllib.parse import parse_qs
    identifier=(parse_qs(parsed.query).get("cid") or [host])[0]
   elif provider=="ukg":
    parts=path.split("/")
    identifier="|".join([host]+parts[:2]) if parts else host
   elif provider in {"oracle","successfactors","paycom","bullhorn","clearcompany","applicantpro","fountain","hirebridge","jobdiva","zoho_recruit","manatal","applitrack","hireology","paycor","peopleadmin","isolved","hibob","gohire","hiringthing","homerun","pageup","trinet","dover","hirehive","kula","rival","werecruit","deel","firststage","recruiterbox","talentbrew","radancy","paradox","brassring","applicantstack","jazzhr_alt","ceipal","trakstar_hire","neogov","schooljobs","higheredjobs","applynow","talentreef","icims_alt","jobappnetwork","myworkchoice","ultipro_ukg"}:
    identifier=host
   return provider,identifier or None
 return None,None

def learn_from_jobs(jobs,registry):
 """Learn reusable public ATS board identifiers from broad-discovery results."""
 added=[]
 for job in jobs:
  provider,identifier=detect_ats(job.get("original_url") or job.get("url") or "")
  if not provider or not identifier:continue
  rows=registry.setdefault(provider,[])
  if any((x.get("identifier") or x.get("board_token") or x.get("site") or x.get("board_name") or x.get("company_identifier"))==identifier for x in rows):continue
  company=job.get("company_key") or job.get("company") or "Unknown"
  # Preserve the employer name when broad discovery also provides a display name.
  alt_company=job.get("company")
  if alt_company and str(company).lower()==str(identifier).lower():
   company=alt_company
  row={"company":company,"identifier":identifier,"learned_from":job.get("source"),"original_url":job.get("original_url") or job.get("url")}
  if provider=="workday":
   parsed=urlparse(job.get("original_url") or job.get("url") or "")
   row["host"]=parsed.netloc
   row["locale"]="en-US"
  rows.append(row);added.append({"provider":provider,**row})
 return added

def _reusable_search_url(provider,url):
 """Turn a discovered job-detail URL into the broadest safe public board URL we know."""
 if not url:return url
 p=urlparse(url);host=p.netloc;parts=[x for x in p.path.split("/") if x]
 if provider=="workable" and parts:return f"{p.scheme}://{host}/{parts[0]}/"
 if provider=="jazzhr":return f"{p.scheme}://{host}/"
 if provider=="avature":
  # Avature detail links commonly use /<locale>/careers/JobDetail/<id>.
  if "careers" in parts:
   i=parts.index("careers");return f"{p.scheme}://{host}/"+"/".join(parts[:i+1])+"/"
 if provider=="ukg":
  # Preserve tenant + JobBoard UUID, drop OpportunityDetail/job UUID.
  try:
   i=parts.index("JobBoard")
   if len(parts)>i+1:return f"{p.scheme}://{host}/"+"/".join(parts[:i+2])+"/"
  except ValueError:pass
 if provider=="adp_workforce_now":
  # The ADP recruitment shell is the reusable board; query cid identifies employer.
  from urllib.parse import parse_qs,urlencode
  q=parse_qs(p.query);keep={k:q[k][0] for k in ("cid","ccId","lang") if q.get(k)}
  return f"{p.scheme}://{host}{p.path}"+(("?"+urlencode(keep)) if keep else "")
 if provider=="paylocity" and len(parts)>=2:
  return f"{p.scheme}://{host}/Recruiting/Jobs/"
 return url

def as_discovery_config(registry):
 out={k:[] for k in PATTERNS}
 for x in registry.get("greenhouse",[]):out["greenhouse"].append({"company":x.get("company"),"board_token":x.get("identifier") or x.get("board_token")})
 for x in registry.get("lever",[]):out["lever"].append({"company":x.get("company"),"site":x.get("identifier") or x.get("site")})
 for x in registry.get("ashby",[]):out["ashby"].append({"company":x.get("company"),"board_name":x.get("identifier") or x.get("board_name")})
 for x in registry.get("smartrecruiters",[]):out["smartrecruiters"].append({"company":x.get("company"),"company_identifier":x.get("identifier") or x.get("company_identifier")})
 for provider in ("applitrack","hireology","paycor","peopleadmin","isolved","hibob","gohire","hiringthing","homerun","pageup","trinet","dover","gem","polymer","hirehive","kula","rival","werecruit","deel","firststage","recruiterbox","talentbrew","radancy","paradox","eightfold","successfactors","oracle","ukg","paycom","bullhorn","comeet","clearcompany","applicantpro","fountain","hirebridge","jobdiva","zoho_recruit","manatal","join","greenhouse_eu","dayforce","jobvite","ultipro","recruiting_com","adp_workforce_now","workable","recruitee","teamtailor","bamboohr","phenom","avature","taleo","cornerstone","jazzhr","breezyhr","paylocity","rippling","pinpoint","brassring","careerplug","freshteam","jobscore","personio","applicantstack","jazzhr_alt","ceipal","trakstar_hire","neogov","schooljobs","higheredjobs","applynow","talentreef","icims_alt","jobappnetwork","myworkchoice","ultipro_ukg"):
  for x in registry.get(provider,[]):
   url=x.get("original_url") or x.get("url")
   url=_reusable_search_url(provider,url)
   if url:out[provider].append({"company":x.get("company"),"search_url":url,"job_url_pattern":r".+"})
 for x in registry.get("workday",[]):
  identifier=x.get("identifier") or ""
  parts=identifier.split("|",1)
  if len(parts)!=2:continue
  tenant,site=parts
  host=x.get("host")
  if not host:continue
  out["workday"].append({"company":x.get("company"),"host":host,"tenant":tenant,"site":site,"locale":x.get("locale","en-US")})
 return out
