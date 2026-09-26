from __future__ import annotations
import re
from urllib import request
from urllib.parse import urljoin, urlsplit, unquote
from app.source_registry import detect_ats

ATS_HOST_HINTS=("greenhouse.io","boards.greenhouse.io","job-boards.greenhouse.io","lever.co","jobs.lever.co","ashbyhq.com","jobs.ashbyhq.com","smartrecruiters.com","jobs.smartrecruiters.com","myworkdayjobs.com","myworkdaysite.com","icims.com","jobs.icims.com","jobvite.com","jobs.jobvite.com","dayforcehcm.com","dayforce.com","ultipro.com","recruiting.com","workforcenow.adp.com","jobs.adp.com","successfactors.com","successfactors.eu","oraclecloud.com","oracle.com","eightfold.ai","phenompeople.com","workable.com","apply.workable.com","teamtailor.com","recruitee.com","bamboohr.com","breezy.hr","rippling.com","pinpointhq.com","careerplug.com","freshteam.com","jobscore.com","personio.com","comeet.com","neogov.com","governmentjobs.com","applicantpro.com","hirebridge.com","zoho.com","manatal.com","join.com","applitrack.com","hireology.com","paycor.com","peopleadmin.com","isolvedhire.com","hibob.com","gohire.io","hiringthing.com","homerun.co","pageuppeople.com","dover.com","gem.com","polymer.co","hirehive.com","deel.com","applicantstack.com","ceipal.com","trakstar.com","taleo.net","brassring.com","paycomonline.net","bullhornstaffing.com","jobdiva.com")
APPLY_KEY_RE=re.compile(r'(?i)(?:external)?apply(?:url|link)|application(?:url|link)|redirect(?:url|link)|applyUrl')

def _fetch(url):
 if not url:return ""
 try:
  req=request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; AI-Job-Search-Agent/1.0)"})
  with request.urlopen(req,timeout=20) as resp:return resp.read().decode("utf-8",errors="replace")
 except Exception:return ""

def _same_company_hint(job,url):
 company=re.sub(r"[^a-z0-9]","",(job.get("company_key") or job.get("company") or "").lower())
 host=re.sub(r"[^a-z0-9]","",urlsplit(url).netloc.lower())
 return not company or company[:8] in host or any(x in url.lower() for x in re.findall(r"[a-z0-9]{4,}",(job.get("company_key") or "").lower())[:2])

def _candidate_links(page,base):
 links=[]
 # Aggregators frequently hide the employer ATS URL in JSON/script state instead
 # of a clickable anchor. Normalize escaped slashes and inspect both forms.
 value=(page or "").replace(r"\/", "/").replace(r"\u002F", "/")
 raw=[]
 raw.extend(re.findall(r'''(?i)href=["']([^"'#]+)["']''',value))
 raw.extend(re.findall(r'''(?i)https?://[^"'<>\\\s]+''',value))
 # Prefer URLs explicitly stored in apply/application/redirect JSON properties.
 raw.extend(m.group(1) for m in re.finditer(
  r'''(?i)(?:external)?apply(?:url|link)|application(?:url|link)|redirect(?:url|link)'''+
  r'''[^:]{0,30}:\s*["'](https?://[^"']+)["']''', value))
 for href in raw:
  u=unquote(urljoin(base,href)).rstrip("),.;")
  if any(host in u.lower() for host in ATS_HOST_HINTS):links.append(u)
 return list(dict.fromkeys(links))

def resolve_original_ats(job):
 """Best-effort resolution from aggregator/detail URL to an employer ATS URL; no LLM and no application action."""
 out=dict(job);start=job.get("original_url") or job.get("url") or ""
 out["original_url"]=start
 provider,identifier=detect_ats(start)
 if provider:
  out.update({"original_url":start,"ats_provider":provider,"ats_identifier":identifier,"ats_resolution":"direct"})
  return out
 page=_fetch(start)
 links=_candidate_links(page,start)
 candidates=[]
 for link in links:
  provider,identifier=detect_ats(link)
  if provider:candidates.append((0 if _same_company_hint(job,link) else 1,link,provider,identifier))
 for _,link,provider,identifier in sorted(candidates,key=lambda x:x[0]):
  out.update({"original_url":link,"ats_provider":provider,"ats_identifier":identifier,"ats_resolution":"linked_from_discovery_page"})
  return out
 out["ats_resolution"]="unresolved"
 return out
