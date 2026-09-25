from __future__ import annotations
"""Authoritative/public feeders for the open-ended U.S. employer universe.

Feeders return company identities. They do NOT decide job eligibility and do
not make the resulting company set an allowlist.

SEC is an identity-level feeder for public registrants. Census BDS is deliberately
not treated as a company-name feeder because its public tables are aggregate and
confidentiality-protected rather than an enumeration of individual employers.
"""
import json
from urllib.request import Request,urlopen

SEC_TICKERS="https://www.sec.gov/files/company_tickers.json"
UA={"User-Agent":"AI-Job-Search-Agent/1.0 contact=job-search-agent"}

def sec_public_companies(timeout=30):
    req=Request(SEC_TICKERS,headers=UA)
    with urlopen(req,timeout=timeout) as r:data=json.load(r)
    out=[]
    for row in data.values():
        name=(row.get("title") or "").strip()
        if name:
            out.append({"company":name,"cik":str(row.get("cik_str") or ""),"ticker":row.get("ticker"),
                        "discovered_by":"sec_company_tickers"})
    return out

FEEDERS={"sec_public_companies":sec_public_companies}

def collect(enabled=None):
    enabled=enabled or list(FEEDERS)
    rows=[];errors=[]
    for name in enabled:
        fn=FEEDERS.get(name)
        if not fn:continue
        try:rows.extend(fn())
        except Exception as e:errors.append({"feeder":name,"error":str(e)})
    return rows,errors
