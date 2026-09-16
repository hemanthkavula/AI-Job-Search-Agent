from __future__ import annotations
import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode

BASE = "https://api.ashbyhq.com/posting-api/job-board"

def fetch_jobs(board_name: str, timeout: int = 20) -> list[dict]:
    url=f"{BASE}/{board_name}?{urlencode({'includeCompensation':'true'})}"
    req=Request(url,headers={"Accept":"application/json","User-Agent":"AI-Job-Search-Agent/0.2"})
    with urlopen(req,timeout=timeout) as resp:
        payload=json.loads(resp.read().decode("utf-8"))
    out=[]
    for j in payload.get("jobs",[]):
        out.append({
            "external_id":f"ashby:{board_name}:{j.get('jobUrl') or j.get('applyUrl')}",
            "source":"ashby",
            "company_key":board_name,
            "title":j.get("title",""),
            "location":j.get("location"),
            "url":j.get("jobUrl") or j.get("applyUrl"),
            "description":j.get("descriptionPlain") or j.get("descriptionHtml") or "",
            "updated_at":j.get("publishedAt"),
            "compensation":j.get("compensation"),
        })
    return out
