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

def json_catalog(url, name_field="name", timeout=30):
    """Generic adapter for vetted public JSON organization catalogs.

    A catalog must be explicitly configured; this does not crawl arbitrary
    directories or infer company identities.
    """
    req=Request(url,headers=UA)
    with urlopen(req,timeout=timeout) as r:data=json.load(r)
    rows=data if isinstance(data,list) else data.get("results") or data.get("data") or []
    out=[]
    for row in rows:
        if not isinstance(row,dict):continue
        name=(row.get(name_field) or "").strip()
        if name:out.append({"company":name,"discovered_by":"public_json_catalog"})
    return out

def fdic_insured_banks(timeout=30):
    """Active FDIC-insured institutions. The FDIC institutions endpoint also
    exposes institution website fields when available, which can become trusted
    domain evidence downstream."""
    url="https://banks.data.fdic.gov/bankfind-suite/api/institutions?filters=ACTIVE%3A1&fields=NAME,CERT,WEBADDR&limit=10000&format=json"
    req=Request(url,headers=UA)
    with urlopen(req,timeout=timeout) as r:data=json.load(r)
    out=[]
    for item in data.get("data",[]):
        row=item.get("data",item) if isinstance(item,dict) else {}
        name=(row.get("NAME") or "").strip()
        if not name:continue
        web=(row.get("WEBADDR") or "").strip()
        out.append({"company":name,"fdic_cert":str(row.get("CERT") or ""),
                    "official_url":web or None,"discovered_by":"fdic_active_institutions"})
    return out

def college_scorecard_institutions(timeout=30):
    """U.S. higher-education institutions from the Department of Education
    College Scorecard public API. Requires COLLEGE_SCORECARD_API_KEY."""
    import os
    key=os.getenv("COLLEGE_SCORECARD_API_KEY")
    if not key:return []
    url=("https://api.data.gov/ed/collegescorecard/v1/schools.json"
         "?school.operating=1&fields=id,school.name,school.school_url&per_page=100"
         f"&api_key={key}")
    out=[];page=0
    while True:
        req=Request(url+f"&page={page}",headers=UA)
        with urlopen(req,timeout=timeout) as r:data=json.load(r)
        rows=data.get("results") or []
        if not rows:break
        for row in rows:
            name=(row.get("school.name") or "").strip()
            if not name:continue
            web=(row.get("school.school_url") or "").strip()
            out.append({"company":name,"education_id":str(row.get("id") or ""),
                        "official_url":web or None,
                        "discovered_by":"college_scorecard"})
        meta=data.get("metadata") or {}
        total=int(meta.get("total") or 0)
        page+=1
        if page*100>=total:break
    return out

def cms_hospitals(timeout=30):
    """Hospital organizations from CMS Provider Data API.

    This is an organization-identity feeder. CMS data is authoritative for
    participating facilities, but facility website availability varies, so
    official domains are resolved separately unless a website is present.
    """
    url=("https://data.cms.gov/provider-data/api/1/datastore/sql"
         "?query=SELECT%20facility_id,facility_name,address,city,state,zip_code"
         "%20FROM%20xubh-q36u%20LIMIT%2050000")
    req=Request(url,headers=UA)
    with urlopen(req,timeout=timeout) as r:data=json.load(r)
    rows=data if isinstance(data,list) else data.get("results") or data.get("data") or []
    out=[]
    for row in rows:
        if not isinstance(row,dict):continue
        name=(row.get("facility_name") or row.get("Facility Name") or "").strip()
        if not name:continue
        out.append({"company":name,
                    "cms_facility_id":str(row.get("facility_id") or row.get("Facility ID") or ""),
                    "state":row.get("state") or row.get("State"),
                    "discovered_by":"cms_hospital_general_information"})
    return out

FEEDERS={"sec_public_companies":sec_public_companies,"fdic_insured_banks":fdic_insured_banks,
         "college_scorecard_institutions":college_scorecard_institutions,
         "cms_hospitals":cms_hospitals}

def collect(enabled=None):
    enabled=enabled or list(FEEDERS)
    rows=[];errors=[]
    for name in enabled:
        fn=FEEDERS.get(name)
        if not fn:continue
        try:rows.extend(fn())
        except Exception as e:errors.append({"feeder":name,"error":str(e)})
    return rows,errors
