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
UA={"User-Agent":"AI-Job-Search-Agent/1.0 (employer-source discovery; contact: hemanthkavula/AI-Job-Search-Agent)","Accept":"application/json"}

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
    """Active FDIC-insured institutions with institution-reported websites."""
    from urllib.parse import urlencode
    base="https://api.fdic.gov/banks/institutions"
    out=[];offset=0;limit=1000
    while True:
        qs=urlencode({"filters":"ACTIVE:1","fields":"NAME,CERT,WEBADDR",
                      "limit":limit,"offset":offset})
        req=Request(base+"?"+qs,headers={**UA,"Accept":"application/json"})
        with urlopen(req,timeout=timeout) as r:
            raw=r.read()
            content_type=r.headers.get("Content-Type","")
            status=getattr(r,"status",None)
        try:
            data=json.loads(raw.decode("utf-8"))
        except Exception as e:
            preview=raw[:160].decode("utf-8","replace").replace("\\n"," ")
            raise RuntimeError(f"FDIC institutions response was not valid JSON (status={status}, content_type={content_type}, preview={preview!r})") from e
        rows=data.get("data") or []
        if not rows:break
        for item in rows:
            row=item.get("data",item) if isinstance(item,dict) else {}
            name=(row.get("NAME") or "").strip()
            if not name:continue
            web=(row.get("WEBADDR") or "").strip()
            out.append({"company":name,"fdic_cert":str(row.get("CERT") or ""),
                        "official_url":web or None,"discovered_by":"fdic_active_institutions"})
        offset+=len(rows)
        total=int(((data.get("meta") or data.get("metadata") or {}).get("total")) or 0)
        if len(rows)<limit or (total and offset>=total):break
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
    """Hospital organizations from CMS Provider Data Catalog.

    Uses the stable dataset-ID query endpoint rather than a distribution-level
    SQL query. CMS documents dataset IDs as stable across refreshes and caps
    query batches, so this adapter paginates explicitly.
    """
    from urllib.parse import urlencode
    base="https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"
    out=[];offset=0;limit=1500
    while True:
        qs=urlencode({"offset":offset,"limit":limit})
        req=Request(base+"?"+qs,headers=UA)
        with urlopen(req,timeout=timeout) as r:data=json.load(r)
        rows=data.get("results") or data.get("data") or []
        if not rows:break
        for item in rows:
            row=item.get("data",item) if isinstance(item,dict) else {}
            if not isinstance(row,dict):continue
            name=(row.get("facility_name") or row.get("Facility Name") or "").strip()
            if not name:continue
            out.append({"company":name,
                        "cms_facility_id":str(row.get("facility_id") or row.get("Facility ID") or ""),
                        "state":row.get("state") or row.get("State"),
                        "discovered_by":"cms_hospital_general_information"})
        offset+=len(rows)
        if len(rows)<limit:break
    return out


def ncua_active_credit_unions(timeout=30):
    """Active federally insured credit unions from NCUA's latest quarterly list.

    NCUA publishes this as a ZIP containing a spreadsheet.  This feeder is
    deliberately dependency-light: it reads the XLSX workbook XML directly and
    returns employer identities only.  Career/ATS resolution remains a separate
    verification step.
    """
    import io, re, zipfile
    from xml.etree import ElementTree as ET
    index="https://ncua.gov/analysis/credit-union-corporate-call-report-data"
    req=Request(index,headers=UA)
    with urlopen(req,timeout=timeout) as r:html=r.read().decode("utf-8","ignore")
    m=re.search(r'href=["\\\']([^"\\\']*federally-insured-credit-union-list[^"\\\']*\.zip)["\\\']',html,re.I)
    if not m:raise RuntimeError("NCUA federally insured credit union ZIP link not found")
    from urllib.parse import urljoin
    zip_url=urljoin(index,m.group(1))
    with urlopen(Request(zip_url,headers=UA),timeout=timeout) as r:payload=r.read()
    z=zipfile.ZipFile(io.BytesIO(payload))
    xlsx=next((n for n in z.namelist() if n.lower().endswith(".xlsx")),None)
    if not xlsx:return []
    book=zipfile.ZipFile(io.BytesIO(z.read(xlsx)))
    ns={"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared=[]
    if "xl/sharedStrings.xml" in book.namelist():
        root=ET.fromstring(book.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si",ns):
            shared.append("".join(t.text or "" for t in si.iterfind(".//m:t",ns)))
    sheet=next((n for n in book.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")),None)
    if not sheet:return []
    root=ET.fromstring(book.read(sheet))
    rows=[]
    for row in root.findall(".//m:row",ns):
        vals=[]
        for cell in row.findall("m:c",ns):
            v=cell.find("m:v",ns);value="" if v is None else (v.text or "")
            if cell.get("t")=="s" and value.isdigit() and int(value)<len(shared):value=shared[int(value)]
            vals.append(value.strip())
        if vals:rows.append(vals)
    if not rows:return []
    header=[x.upper().replace(" ","_") for x in rows[0]]
    name_idx=next((i for i,x in enumerate(header) if x in {"CU_NAME","CREDIT_UNION_NAME","NAME"}),None)
    number_idx=next((i for i,x in enumerate(header) if x in {"CU_NUMBER","CHARTER_NUMBER","CHARTER"}),None)
    if name_idx is None:return []
    out=[]
    for vals in rows[1:]:
        if name_idx>=len(vals):continue
        name=vals[name_idx].strip()
        if not name:continue
        number=vals[number_idx].strip() if number_idx is not None and number_idx<len(vals) else ""
        out.append({"company":name,"ncua_charter":number or None,
                    "discovered_by":"ncua_active_federally_insured_credit_unions"})
    return out

def sam_registered_entities(timeout=30):
    """Private/public organizations registered in SAM.gov.

    Requires SAM_API_KEY. This is an employer-identity expansion feed, not proof
    that an entity is hiring and not an eligibility allowlist.
    """
    import os
    from urllib.parse import urlencode
    key=os.getenv("SAM_API_KEY")
    if not key:return []
    base="https://api.sam.gov/entity-information/v3/entities"
    out=[];offset=0;limit=100
    # Bound each scheduled refresh; persistent registry accumulates identities.
    for _ in range(20):
        qs=urlencode({"api_key":key,"registrationStatus":"A","purposeOfRegistrationCode":"Z2",
                      "includeSections":"entityRegistration,coreData","offset":offset,"limit":limit})
        req=Request(base+"?"+qs,headers=UA)
        with urlopen(req,timeout=timeout) as r:data=json.load(r)
        rows=data.get("entityData") or data.get("entityDataList") or []
        if not rows:break
        for item in rows:
            reg=item.get("entityRegistration") or item.get("entityRegistrationData") or {}
            name=(reg.get("legalBusinessName") or "").strip()
            if not name:continue
            core=item.get("coreData") or {}
            info=core.get("entityInformation") or {}
            web=(info.get("entityURL") or "").strip()
            out.append({"company":name,"uei":reg.get("ueiSAM"),
                        "official_url":web or None,
                        "discovered_by":"sam_registered_entities"})
        offset+=len(rows)
        if len(rows)<limit:break
    return out


def dol_h1b_employers(timeout=60):
    """Recent employers with certified H-1B LCAs from the latest DOL OFLC LCA disclosure.

    This is sponsorship-history evidence only. It never overrides current-job
    sponsorship, work-authorization, citizenship, or clearance filters.
    """
    import io, re
    from urllib.parse import urljoin, urlparse
    page="https://www.dol.gov/agencies/eta/foreign-labor/performance"
    with urlopen(Request(page,headers=UA),timeout=timeout) as r:
        body=r.read().decode("utf-8","ignore")

    # DOL has historically used both "Disclosure" and the live FY2026
    # "Dislclosure" spelling. Discover candidates semantically instead of
    # hard-coding either spelling, and select the newest FY/quarter.
    links=[]
    for raw in re.findall(r'href=["\\\']([^"\\\']+\\.xlsx(?:\\?[^"\\\']*)?)["\\\']',body,re.I):
        url=urljoin(page,raw)
        name=urlparse(url).path.rsplit("/",1)[-1]
        low=name.lower()
        if not low.startswith("lca_"):continue
        if any(x in low for x in ("appendix","worksite","record_layout")):continue
        m=re.search(r'fy(\\d{4})(?:_q(\\d))?',low,re.I)
        if not m:continue
        links.append((int(m.group(1)),int(m.group(2) or 4),url,name))
    if not links:
        raise RuntimeError("No DOL LCA disclosure workbook link found on OFLC performance page")
    _,_,workbook_url,workbook_name=max(links,key=lambda x:(x[0],x[1]))

    payload=urlopen(Request(workbook_url,headers=UA),timeout=timeout).read()
    import openpyxl
    try:
        wb=openpyxl.load_workbook(io.BytesIO(payload),read_only=True,data_only=True)
    except Exception as e:
        raise RuntimeError(f"DOL LCA workbook could not be parsed ({workbook_name}): {e}") from e
    ws=wb.active
    rows=ws.iter_rows(values_only=True)
    try:
        header=[str(x or "").strip().upper() for x in next(rows)]
    except StopIteration as e:
        raise RuntimeError(f"DOL LCA workbook is empty: {workbook_name}") from e
    idx={name:i for i,name in enumerate(header)}
    required={"EMPLOYER_NAME","CASE_STATUS","VISA_CLASS"}
    missing=sorted(required-set(idx))
    if missing:
        raise RuntimeError("DOL LCA workbook missing required columns: "+", ".join(missing))
    seen=set();out=[]
    for vals in rows:
        status=re.sub(r"\\s+","-",str(vals[idx["CASE_STATUS"]] or "").strip().upper())
        visa=str(vals[idx["VISA_CLASS"]] or "").strip().upper()
        name=str(vals[idx["EMPLOYER_NAME"]] or "").strip()
        if status not in {"CERTIFIED","CERTIFIED-WITHDRAWN"} or visa!="H-1B" or not name:continue
        key=name.casefold()
        if key in seen:continue
        seen.add(key)
        out.append({"company":name,"recent_h1b_lca":True,
                    "h1b_disclosure_file":workbook_name,
                    "discovered_by":"dol_oflc_latest_h1b_lca"})
    return out

FEEDERS={"sec_public_companies":sec_public_companies,"dol_h1b_employers":dol_h1b_employers,"fdic_insured_banks":fdic_insured_banks,
         "ncua_active_credit_unions":ncua_active_credit_unions,
         "college_scorecard_institutions":college_scorecard_institutions,
         "cms_hospitals":cms_hospitals,"sam_registered_entities":sam_registered_entities}
def collect(enabled=None):
    enabled=enabled or list(FEEDERS)
    rows=[];errors=[]
    for name in enabled:
        fn=FEEDERS.get(name)
        if not fn:continue
        try:rows.extend(fn())
        except Exception as e:errors.append({"feeder":name,"error":str(e)})
    return rows,errors
