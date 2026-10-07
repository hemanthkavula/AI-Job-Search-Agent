from __future__ import annotations
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_PATH=str(Path(os.getenv("JOB_AGENT_STATE_DIR","generated"))/"company_registry.json")
AGGREGATOR_HOSTS=("dice.com","indeed.com","linkedin.com","ziprecruiter.com","monster.com","wellfound.com","builtin.com","ycombinator.com")

def _is_aggregator_url(value):
    try:
        host=(urlparse(str(value or "")).netloc or "").lower()
    except Exception:
        return False
    return any(host==x or host.endswith("."+x) for x in AGGREGATOR_HOSTS)

def sanitize_aggregator_evidence(registry):
    """Prevent job-board URLs from masquerading as employer career/domain evidence."""
    for row in (registry or {}).values():
        if not isinstance(row,dict):continue
        for field in ("careers_url","official_url"):
            if row.get(field) and _is_aggregator_url(row.get(field)):
                row["aggregator_"+field]=row.get(field)
                row.pop(field,None)
        if row.get("official_domain") and any(
            str(row.get("official_domain")).lower()==h or str(row.get("official_domain")).lower().endswith("."+h)
            for h in AGGREGATOR_HOSTS
        ):
            row.pop("official_domain",None)
        evidence=row.get("organization_url_evidence")
        if evidence and _is_aggregator_url(evidence):
            row["aggregator_company_url"]=evidence
            row.pop("organization_url_evidence",None)
            row.pop("organization_url_evidence_source",None)
        candidate=row.get("domain_candidate_url")
        if candidate and _is_aggregator_url(candidate):
            row.pop("domain_candidate_url",None)
            row.pop("domain_candidate_host",None)
            row.pop("domain_candidate_evidence",None)
    return registry

def load(path=DEFAULT_PATH):
    p=Path(path)
    if not p.exists(): return {}
    try:return sanitize_aggregator_evidence(json.loads(p.read_text(encoding="utf-8")))
    except Exception:return {}

def save(registry,path=DEFAULT_PATH):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(registry,indent=2,sort_keys=True),encoding="utf-8")

def company_key(company):
    """Normalize common legal/name noise so one employer does not fragment."""
    s=unicodedata.normalize("NFKD",str(company or "")).encode("ascii","ignore").decode().lower()
    s=s.replace("&"," and ")
    s=re.sub(r"[^a-z0-9]+"," ",s)
    suffixes=r"(?:incorporated|corporation|company|limited|holdings|holding|group|inc|corp|llc|ltd|plc|lp|llp|co)"
    s=re.sub(r"\\b"+suffixes+r"\\b"," ",s)
    return re.sub(r"\\s+"," ",s).strip()

def upsert(registry, company, official_domain=None, careers_url=None, ats_provider=None, ats_identifier=None, discovered_by=None):
    if not company:return
    key=company_key(company)
    row=registry.setdefault(key,{"company":company})
    for k,v in {"official_domain":official_domain,"careers_url":careers_url,"ats_provider":ats_provider,"ats_identifier":ats_identifier,"discovered_by":discovered_by}.items():
        if v:row[k]=v
    row["last_seen_at"]=datetime.now(timezone.utc).isoformat()

def learn_from_jobs(jobs,registry):
    for j in jobs:
        company=j.get("company") or j.get("company_key")
        # A discovered ATS job proves both current hiring and, when the
        # collector already supplied a verified ATS provider + tenant identifier,
        # a reusable provider source. Persist that URL on the canonical employer
        # record. Unknown/non-ATS job-detail URLs remain evidence only and are not
        # promoted to careers_url.
        source_url=j.get("original_url") or j.get("url")
        verified_ats=bool(
            j.get("ats_provider") and j.get("ats_identifier")
            and (j.get("ats_provider") or "").lower() not in {"dice","indeed","linkedin","ziprecruiter","monster"}
            and not _is_aggregator_url(source_url)
        )
        upsert(registry,company,
               careers_url=source_url if verified_ats else None,
               ats_provider=j.get("ats_provider"),ats_identifier=j.get("ats_identifier"),
               discovered_by=j.get("source"))
        key=company_key(company or "")
        if key in registry:
            registry[key]["current_hiring_signal"]=True
            registry[key]["last_job_seen_at"]=datetime.now(timezone.utc).isoformat()
            registry[key]["last_job_url"]=j.get("original_url") or j.get("url")
        # JobPosting hiringOrganization.url/sameAs is useful identity evidence,
        # but is not accepted as an official domain until the domain resolver
        # verifies the employer name on the first-party destination.
        candidate=j.get("organization_url_evidence")
        key=company_key(company or "")
        if candidate and _is_aggregator_url(candidate):
            if key in registry:registry[key]["aggregator_company_url"]=candidate
            candidate=None
        if candidate and key in registry:
            registry[key]["organization_url_evidence"]=candidate
            registry[key]["organization_url_evidence_source"]="jobposting_hiring_organization"
            # A JobPosting hiringOrganization URL is explicit employer-provided
            # identity evidence. Promote its host immediately as a domain candidate
            # so the enrichment queue does not depend on low-yield name web search.
            try:
                from urllib.parse import urlparse
                normalized=candidate if "://" in candidate else "https://"+candidate
                host=urlparse(normalized).netloc.lower()
                if host.startswith("www."):host=host[4:]
                if host and not registry[key].get("official_domain"):
                    registry[key]["domain_candidate_url"]=normalized
                    registry[key]["domain_candidate_host"]=host
                    registry[key]["domain_candidate_evidence"]="jobposting_hiring_organization"
            except Exception:
                pass
    return registry
