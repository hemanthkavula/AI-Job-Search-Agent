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
 "personio":[r"https?://([^.]+)\.jobs\.personio\.(?:de|com)/"],
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
 for provider,patterns in PATTERNS.items():
  for pat in patterns:
   m=re.search(pat,url,re.I)
   if m:
    if provider=="workday":return provider,"|".join(x for x in m.groups() if x)
    return provider,next((x for x in m.groups() if x),None)
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

def as_discovery_config(registry):
 out={k:[] for k in PATTERNS}
 for x in registry.get("greenhouse",[]):out["greenhouse"].append({"company":x.get("company"),"board_token":x.get("identifier") or x.get("board_token")})
 for x in registry.get("lever",[]):out["lever"].append({"company":x.get("company"),"site":x.get("identifier") or x.get("site")})
 for x in registry.get("ashby",[]):out["ashby"].append({"company":x.get("company"),"board_name":x.get("identifier") or x.get("board_name")})
 for x in registry.get("smartrecruiters",[]):out["smartrecruiters"].append({"company":x.get("company"),"company_identifier":x.get("identifier") or x.get("company_identifier")})
 for provider in ("dayforce","ultipro","recruiting_com","adp_workforce_now","workable","recruitee","teamtailor","bamboohr","phenom","avature","taleo","cornerstone","jazzhr","breezyhr","paylocity","rippling","pinpoint","brassring","careerplug","freshteam","jobscore","personio"):
  for x in registry.get(provider,[]):
   url=x.get("original_url") or x.get("url")
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
