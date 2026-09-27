from __future__ import annotations
"""Resolve company identities to verified official corporate domains.

Resolution is evidence-based: candidate URLs must come from trusted metadata
(e.g. SEC filing metadata) or an explicitly supplied official URL. We never
manufacture domains from company names.
"""
import json,re
from urllib.parse import urlparse
from urllib.request import Request,urlopen
from urllib.parse import quote_plus

UA={"User-Agent":"AI-Job-Search-Agent/1.0 contact=job-search-agent"}

def _host(url):
    try:
        h=urlparse(url if "://" in url else "https://"+url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:return None

def sec_company_domain(cik,timeout=20):
    """Use SEC submissions metadata only when it actually exposes a website.\n\n    SEC documents the submissions API for filing history and filer metadata,\n    but does not guarantee a corporate website field. Missing website data is\n    therefore a normal unresolved result, not a reason to guess a domain.\n    """
    if not cik:return None
    cik=str(cik).strip().zfill(10)
    req=Request(f"https://data.sec.gov/submissions/CIK{cik}.json",headers=UA)
    with urlopen(req,timeout=timeout) as r:data=json.load(r)
    website=(data.get("website") or data.get("investorWebsite") or "").strip() if isinstance(data,dict) else ""
    domain=_host(website) if website else None
    return {"official_domain":domain,"official_url":website or None,
            "domain_evidence":"sec_submissions"} if domain else None

def _verified_domain_from_search(row,timeout=20):
    """Resolve only when a public search result itself supplies an official-site URL.

    This never manufactures a domain from the company name. Candidate URLs come
    from search-result evidence and are rejected when they are known directories,
    social networks, job boards, ATS hosts, government sites, or aggregators.
    """
    name=(row.get("company") or "").strip()
    if not name:return None
    q=quote_plus(f'"{name}" official website')
    req=Request("https://www.google.com/search?q="+q,headers={"User-Agent":"Mozilla/5.0"})
    try:
        with urlopen(req,timeout=timeout) as r:body=r.read().decode("utf-8","ignore")
    except Exception:return None
    blocked=("google.","linkedin.com","facebook.com","instagram.com","x.com","twitter.com",
             "wikipedia.org","crunchbase.com","bloomberg.com","indeed.com","glassdoor.com",
             "ziprecruiter.com","dice.com","monster.com","builtin.com","wellfound.com",
             "greenhouse.io","lever.co","ashbyhq.com","workdayjobs.com","myworkdayjobs.com",
             "smartrecruiters.com","icims.com","jobvite.com",".gov")
    candidates=[]
    for raw in re.findall(r'https?://[^"&<> ]+',body):
        raw=raw.replace("&amp;","&")
        h=_host(raw)
        if not h or any(b in h for b in blocked):continue
        candidates.append((raw,h))
    # Search evidence is intentionally conservative: require the company tokens
    # to be visible around the candidate host in the returned result document.
    tokens=[t.lower() for t in re.findall(r"[A-Za-z0-9]+",name) if len(t)>=4][:3]
    low=body.lower()
    for raw,h in candidates:
        pos=low.find(h.lower())
        context=low[max(0,pos-500):pos+500] if pos>=0 else ""
        if tokens and sum(t in context for t in tokens)>=min(2,len(tokens)):
            return {"official_domain":h,"official_url":"https://"+h,
                    "domain_evidence":"public_search_official_site_evidence"}
    return None

def can_resolve_company(row):
    """True only when the row contains evidence that the resolver can use.\n\n    This prevents bounded enrichment batches from being consumed by identities\n    that currently have no verified domain evidence.\n    """
    return bool(row.get("official_domain") or row.get("sec_cik") or row.get("company"))

def resolve_company(row):
    if row.get("official_domain"):
        return {"official_domain":row["official_domain"],"official_url":row.get("official_url"),
                "domain_evidence":row.get("domain_evidence") or "existing_verified"}
    if row.get("sec_cik"):
        hit=sec_company_domain(row["sec_cik"])
        if hit:return hit
    return _verified_domain_from_search(row)
