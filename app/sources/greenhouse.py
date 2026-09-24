from __future__ import annotations
import html
import json
import time
from urllib.request import urlopen, Request
from urllib.parse import urlencode

BASE = "https://boards-api.greenhouse.io/v1/boards"

def fetch_jobs(board_token: str, timeout: int = 20, retries: int = 3) -> list[dict]:
    """Fetch public Greenhouse jobs with bounded retries for transient timeouts/5xx failures."""
    url = f"{BASE}/{board_token}/jobs?{urlencode({'content':'true'})}"
    last_error=None
    for attempt in range(max(1,retries)):
        try:
            req = Request(url, headers={"User-Agent":"AI-Job-Search-Agent/0.7"})
            with urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:
            last_error=exc
            if attempt + 1 < max(1,retries):
                time.sleep(1.5 * (2 ** attempt))
    else:
        raise last_error or RuntimeError(f"Greenhouse request failed: {board_token}")
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
