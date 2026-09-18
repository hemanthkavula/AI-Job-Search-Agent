from __future__ import annotations
import re
from urllib import request
from urllib.parse import urljoin
from app.source_registry import detect_ats

ATS_HOST_HINTS=("greenhouse.io","lever.co","ashbyhq.com","smartrecruiters.com","myworkdayjobs.com","icims.com")

def _fetch(url):
 if not url:return ""
 try:
  req=request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; AI-Job-Search-Agent/1.0)"})
  with request.urlopen(req,timeout=20) as resp:return resp.read().decode("utf-8",errors="replace")
 except Exception:return ""

def _candidate_links(page,base):
 links=[]
 for href in re.findall(r'''(?i)href=["']([^"'#]+)["']''',page or ""):
  u=urljoin(base,href)
  if any(host in u.lower() for host in ATS_HOST_HINTS):links.append(u)
 return list(dict.fromkeys(links))

def resolve_original_ats(job):
 """Best-effort resolution from aggregator/detail URL to an employer ATS URL; no LLM and no application action."""
 out=dict(job);start=job.get("original_url") or job.get("url") or ""
 provider,identifier=detect_ats(start)
 if provider:
  out.update({"original_url":start,"ats_provider":provider,"ats_identifier":identifier,"ats_resolution":"direct"})
  return out
 page=_fetch(start)
 links=_candidate_links(page,start)
 for link in links:
  provider,identifier=detect_ats(link)
  if provider:
   out.update({"original_url":link,"ats_provider":provider,"ats_identifier":identifier,"ats_resolution":"linked_from_discovery_page"})
   return out
 out["ats_resolution"]="unresolved"
 return out
