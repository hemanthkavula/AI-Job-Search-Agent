from __future__ import annotations
import json, re
from urllib.request import Request, urlopen

UA={"User-Agent":"AI-Job-Search-Agent/0.8","Accept":"text/html,application/xhtml+xml"}

def _get(url: str, timeout: int = 25) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _positions(body: str) -> list[dict]:
    marker='"positions":'
    start=body.find(marker)
    if start < 0:
        return []
    start=body.find("[",start+len(marker))
    if start < 0:
        return []
    depth=0; in_string=False; escape=False
    for i in range(start,len(body)):
        ch=body[i]
        if in_string:
            if escape: escape=False
            elif ch=="\\": escape=True
            elif ch=='"': in_string=False
            continue
        if ch=='"': in_string=True
        elif ch=="[": depth+=1
        elif ch=="]":
            depth-=1
            if depth==0:
                try:return json.loads(body[start:i+1])
                except Exception:return []
    return []

def fetch_jobs(company: str, careers_url: str, timeout: int = 25) -> list[dict]:
    """Fetch public Eightfold career positions embedded in the career page."""
    body=_get(careers_url,timeout)
    out=[]
    for j in _positions(body):
        title=str(j.get("posting_name") or j.get("name") or "")
        desc=str(j.get("job_description") or "")
        hay=(title+" "+desc[:2500]).lower()
        if not any(term in hay for term in ("data engineer","data engineering","data platform engineer","big data engineer","etl engineer")):
            continue
        loc=j.get("location") or ", ".join(j.get("locations") or [])
        ident=j.get("ats_job_id") or j.get("display_job_id") or j.get("id")
        url=j.get("canonicalPositionUrl") or careers_url.rstrip("/")+"/job/"+str(j.get("id") or "")
        out.append({
            "external_id":f"eightfold:{company}:{ident}","source":"eightfold","company_key":company,
            "title":title,"location":loc or None,"url":url,"original_url":url,
            "ats_provider":"eightfold","ats_identifier":careers_url,"job_id":ident,
            "description":desc,"description_complete":bool(desc.strip()),
            "updated_at":j.get("t_update") or j.get("t_create"),
        })
    print(f"Eightfold / {company}: {len(out)} DE jobs",flush=True)
    return out
