from __future__ import annotations
import json
from urllib.request import Request, urlopen

BASE = "https://prod-kong.internal.talentreef.com/apply/proxy-es/search-en-us/posting/_search"

def fetch_jobs(company: str, client_id: str = "", timeout: int = 20, page_size: int = 100, max_pages: int|None = None, search_url: str = "") -> list[dict]:
    if not client_id:
        if not search_url:raise ValueError("TalentReef source requires client_id or verified search_url")
        from app.sources.career_site import fetch_jobs as career_site_jobs
        rows=career_site_jobs(company,search_url,r".+")
        for row in rows:row["source"]="talentreef";row["source_family"]="direct_ats_public_board";row["ats_provider"]="talentreef"
        return rows
    out=[];offset=0;pages=0;truncated=False
    while True:
        if max_pages is not None and pages>=max_pages:truncated=True;break
        body={"query":{"bool":{"filter":[{"term":{"clientId":client_id}},{"term":{"internalOrExternal":"externalOnly"}}]}},"from":offset,"size":page_size}
        req=Request(BASE,data=json.dumps(body).encode("utf-8"),headers={"User-Agent":"AI-Job-Search-Agent/0.7","Content-Type":"application/json","Accept":"application/json"},method="POST")
        with urlopen(req,timeout=timeout) as resp:payload=json.loads(resp.read().decode("utf-8"))
        hits=((payload.get("hits") or {}).get("hits") or []);pages+=1
        if not hits:break
        for hit in hits:
            src=hit.get("_source") or {};job_id=src.get("id") or src.get("postingId") or hit.get("_id");title=src.get("title") or src.get("jobTitle") or src.get("positionTitle") or "";description=src.get("description") or src.get("jobDescription") or "";location=src.get("location") or src.get("locationName") or src.get("city") or ""
            if isinstance(location,dict):location=", ".join(str(location.get(k) or "") for k in ("city","state","country") if location.get(k))
            url=src.get("url") or src.get("applyUrl") or src.get("jobUrl") or src.get("postingUrl")
            out.append({"external_id":f"talentreef:{client_id}:{job_id}","source":"talentreef","source_family":"direct_ats_api","company":src.get("companyName") or src.get("brandName") or company,"company_key":str(client_id),"title":title,"location":location,"url":url,"original_url":url,"ats_provider":"talentreef","ats_identifier":str(client_id),"job_id":job_id,"description":description,"description_complete":bool(description),"employment_type":src.get("employmentType") or src.get("jobType"),"updated_at":src.get("updatedAt") or src.get("dateUpdated") or src.get("postedDate")})
        offset+=len(hits)
        total=(payload.get("hits") or {}).get("total")
        if isinstance(total,dict):total=total.get("value")
        try:total=int(total) if total is not None else None
        except Exception:total=None
        if total is not None and offset>=total:break
        if not hits:break
    print(f"TalentReef / {company}: {len(out)} jobs from {pages} page(s), pagination={'TRUNCATED' if truncated else 'EXHAUSTED'}",flush=True)
    return out
