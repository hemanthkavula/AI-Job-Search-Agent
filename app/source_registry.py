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
  row={"company":job.get("company_key") or job.get("company") or "Unknown","identifier":identifier,"learned_from":job.get("source")}
  if provider=="workday":
   parsed=urlparse(job.get("original_url") or job.get("url") or "")
   row["host"]=parsed.netloc
   row["locale"]="en-US"
  rows.append(row);added.append({"provider":provider,**row})
 return added

def as_discovery_config(registry):
 out={"greenhouse":[],"lever":[],"ashby":[],"smartrecruiters":[],"workday":[]}
 for x in registry.get("greenhouse",[]):out["greenhouse"].append({"company":x.get("company"),"board_token":x.get("identifier") or x.get("board_token")})
 for x in registry.get("lever",[]):out["lever"].append({"company":x.get("company"),"site":x.get("identifier") or x.get("site")})
 for x in registry.get("ashby",[]):out["ashby"].append({"company":x.get("company"),"board_name":x.get("identifier") or x.get("board_name")})
 for x in registry.get("smartrecruiters",[]):out["smartrecruiters"].append({"company":x.get("company"),"company_identifier":x.get("identifier") or x.get("company_identifier")})
 for x in registry.get("workday",[]):
  identifier=x.get("identifier") or ""
  parts=identifier.split("|",1)
  if len(parts)!=2:continue
  tenant,site=parts
  host=x.get("host")
  if not host:continue
  out["workday"].append({"company":x.get("company"),"host":host,"tenant":tenant,"site":site,"locale":x.get("locale","en-US")})
 return out
