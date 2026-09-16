from __future__ import annotations
import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode

BASE = "https://api.lever.co/v0/postings"

def fetch_jobs(site: str, timeout: int = 20) -> list[dict]:
    """Fetch public Lever postings for one company site."""
    url = f"{BASE}/{site}?{urlencode({'mode':'json','limit':100})}"
    req = Request(url, headers={"Accept":"application/json","User-Agent":"AI-Job-Search-Agent/0.2"})
    with urlopen(req, timeout=timeout) as resp:
        payload=json.loads(resp.read().decode("utf-8"))
    out=[]
    for j in payload:
        lists=j.get("lists") or []
        description=" ".join([j.get("descriptionPlain") or "", j.get("additionalPlain") or ""] + [x.get("content","") for x in lists])
        cats=j.get("categories") or {}
        out.append({
            "external_id": f"lever:{site}:{j.get('id')}",
            "source":"lever",
            "company_key":site,
            "title":j.get("text",""),
            "location":cats.get("location"),
            "url":j.get("hostedUrl") or j.get("applyUrl"),
            "description":description,
            "updated_at":None,
        })
    return out
