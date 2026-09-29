from __future__ import annotations
import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote

BASE = "https://api.ashbyhq.com/posting-api/job-board"

def fetch_jobs(board_name: str, timeout: int = 20) -> list[dict]:
    normalized_board=str(board_name or "").strip()
    if not normalized_board:return []
    encoded_board=quote(normalized_board,safe="")
    url=f"{BASE}/{encoded_board}?{urlencode({'includeCompensation':'true'})}"
    req=Request(url,headers={"Accept":"application/json","User-Agent":"AI-Job-Search-Agent/0.2"})
    with urlopen(req,timeout=timeout) as resp:
        payload=json.loads(resp.read().decode("utf-8"))
    out=[]
    for j in payload.get("jobs",[]):
        out.append({
            "external_id":f"ashby:{normalized_board}:{j.get('jobUrl') or j.get('applyUrl')}",
            "source":"ashby",
            "company_key":normalized_board,
            "title":j.get("title",""),
            "location":j.get("location"),
            "url":j.get("jobUrl") or j.get("applyUrl"),
            "description":j.get("descriptionPlain") or j.get("descriptionHtml") or "",
            "updated_at":j.get("publishedAt"),
            "compensation":j.get("compensation"),
        })
    return out
