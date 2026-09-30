from __future__ import annotations
import json, re
from urllib.request import Request, urlopen

UA={"User-Agent":"AI-Job-Search-Agent/0.8","Accept":"text/html,application/xhtml+xml"}

def _get(url: str, timeout: int = 25) -> str:
    with urlopen(Request(url,headers=UA),timeout=timeout) as resp:
        return resp.read().decode("utf-8","replace")

def _positions(body: str) -> list[dict]:
    candidates=[body, body.replace('\\\"','"')]
    for candidate in candidates:
        rows=_positions_from(candidate)
        if rows:return rows
    return []

def _positions_from(body: str) -> list[dict]:
    m=re.search(r'["\\\']positions["\\\']\\s*:\\s*',body,re.I)
    start=m.start() if m else -1
    if start < 0:return []
    start=body.find("[",m.end() if m else start)
    if start < 0:return []
    depth=0;in_string=False;escape=False
    for i in range(start,len(body)):
        ch=body[i]
        if in_string:
            if escape:escape=False
            elif ch=="\\":escape=True
            elif ch=='"':in_string=False
            continue
        if ch=='"':in_string=True
        elif ch=="[":depth+=1
        elif ch=="]":
            depth-=1
            if depth==0:
                try:return json.loads(body[start:i+1])
                except Exception:return []
    return []

def _next_data_positions(body: str) -> list[dict]:
    for raw in re.findall(r'<script[^>]+id=["\\\']__NEXT_DATA__["\\\'][^>]*>(.*?)</script>',body,re.I|re.S):
        try:data=json.loads(raw)
        except Exception:continue
        stack=[data]
        while stack:
            node=stack.pop()
            if isinstance(node,dict):
                value=node.get("positions")
                if isinstance(value,list) and value:return value
                stack.extend(node.values())
            elif isinstance(node,list):stack.extend(node)
    return []

def fetch_jobs(company: str, careers_url: str, timeout: int = 25) -> list[dict]:
    """Fetch every public Eightfold position embedded in the employer career page.

    Job-family filtering is deliberately deferred to the shared downstream classifier
    so long/specialized Data Engineer titles and adjacent DE roles cannot be discarded
    by an adapter-specific vocabulary before qualification.
    """
    body=_get(careers_url,timeout);out=[];seen=set()
    positions=_positions(body) or _next_data_positions(body)
    for j in positions:
        title=str(j.get("posting_name") or j.get("name") or "")
        desc=str(j.get("job_description") or "")
        ident=j.get("ats_job_id") or j.get("display_job_id") or j.get("id")
        url=j.get("canonicalPositionUrl") or careers_url.rstrip("/")+"/job/"+str(j.get("id") or "")
        stable=str(ident or url)
        if not stable or stable in seen:continue
        seen.add(stable)
        loc=j.get("location") or ", ".join(j.get("locations") or [])
        out.append({"external_id":f"eightfold:{company}:{stable}","source":"eightfold","company_key":company,"title":title,"location":loc or None,"url":url,"original_url":url,"ats_provider":"eightfold","ats_identifier":careers_url,"job_id":ident,"description":desc,"description_complete":bool(desc.strip()),"updated_at":j.get("t_update") or j.get("t_create")})
    print(f"Eightfold / {company}: {len(out)} live postings collected; job-family filtering deferred downstream",flush=True)
    return out
