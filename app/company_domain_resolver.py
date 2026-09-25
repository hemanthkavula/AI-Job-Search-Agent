from __future__ import annotations
"""Resolve company identities to verified official corporate domains.

Resolution is evidence-based: candidate URLs must come from trusted metadata
(e.g. SEC filing metadata) or an explicitly supplied official URL. We never
manufacture domains from company names.
"""
import json
from urllib.parse import urlparse
from urllib.request import Request,urlopen

UA={"User-Agent":"AI-Job-Search-Agent/1.0 contact=job-search-agent"}

def _host(url):
    try:
        h=urlparse(url if "://" in url else "https://"+url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:return None

def sec_company_domain(cik,timeout=20):
    """Use SEC company submissions metadata as trusted identity evidence."""
    if not cik:return None
    cik=str(cik).strip().zfill(10)
    req=Request(f"https://data.sec.gov/submissions/CIK{cik}.json",headers=UA)
    with urlopen(req,timeout=timeout) as r:data=json.load(r)
    website=(data.get("website") or data.get("investorWebsite") or "").strip()
    domain=_host(website) if website else None
    return {"official_domain":domain,"official_url":website or None,
            "domain_evidence":"sec_submissions"} if domain else None

def resolve_company(row):
    if row.get("official_domain"):
        return {"official_domain":row["official_domain"],"official_url":row.get("official_url"),
                "domain_evidence":row.get("domain_evidence") or "existing_verified"}
    if row.get("sec_cik"):
        return sec_company_domain(row["sec_cik"])
    return None
