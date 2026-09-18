from __future__ import annotations
import html
import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode

BASE = "https://boards-api.greenhouse.io/v1/boards"

def fetch_jobs(board_token: str, timeout: int = 20) -> list[dict]:
    """Fetch public jobs from a Greenhouse board. GET endpoints require no auth."""
    url = f"{BASE}/{board_token}/jobs?{urlencode({'content':'true'})}"
    req = Request(url, headers={"User-Agent":"AI-Job-Search-Agent/0.2"})
    with urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    out=[]
    for j in payload.get("jobs", []):
        out.append({
            "external_id": f"greenhouse:{board_token}:{j.get('id')}",
            "source": "greenhouse",
            "company_key": board_token,
            "title": j.get("title",""),
            "location": (j.get("location") or {}).get("name"),
            "url": j.get("absolute_url"),
            "original_url": j.get("absolute_url"),
            "ats_provider":"greenhouse","ats_identifier":board_token,
            "job_id":j.get("id"),"requisition_id":j.get("requisition_id"),
            "description": html.unescape(j.get("content") or ""),
            "description_complete": bool(j.get("content")),
            "updated_at": j.get("updated_at"),
        })
    return out
