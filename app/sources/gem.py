from __future__ import annotations
import json, re
from html import unescape
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ENDPOINT = "https://jobs.gem.com/api/public/graphql"
QUERY = """query JobBoardList($boardId: String!) {
  oatsExternalJobPostings(boardId: $boardId) {
    jobPostings {
      id extId title
      locations { id name city isoCountry isRemote extId }
      job { id department { id name extId } locationType employmentType }
    }
  }
  jobBoardExternal(vanityUrlPath: $boardId) { id teamDisplayName pageTitle }
}"""
DE_TITLE_PATTERNS=("data engineer","data platform engineer","big data engineer","cloud data engineer","aws data engineer","azure data engineer","data analytics engineer","data integration engineer","data infrastructure engineer","data pipeline engineer","etl engineer","analytics engineer","database engineer")

def _post(payload: dict, timeout: int) -> dict:
    req=Request(ENDPOINT,data=json.dumps(payload).encode(),headers={"Accept":"application/json","Content-Type":"application/json","User-Agent":"AI-Job-Search-Agent/0.4"},method="POST")
    with urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode("utf-8"))

def _plain(v):
    return re.sub(r"\\s+"," ",unescape(str(v or ""))).strip()

def _is_de(title):
    t=_plain(title).lower()
    return any(x in t for x in DE_TITLE_PATTERNS)

def fetch_jobs(company: str, board_url: str, timeout: int=20) -> list[dict]:
    board=urlparse(board_url).path.strip("/").split("/")[0]
    if not board:return []
    payload=_post({"operationName":"JobBoardList","variables":{"boardId":board},"query":QUERY},timeout)
    if payload.get("errors"):raise RuntimeError("Gem GraphQL: "+"; ".join(str(x.get("message") or x) for x in payload["errors"]))
    data=payload.get("data") or {}
    block=data.get("oatsExternalJobPostings") or {}
    rows=block.get("jobPostings") or []
    meta=data.get("jobBoardExternal") or {}
    employer=meta.get("teamDisplayName") or company
    out=[]
    for row in rows:
        title=_plain(row.get("title"))
        if not _is_de(title):continue
        locs=row.get("locations") or []
        loc=", ".join(_plain(x.get("name") or x.get("city")) for x in locs if _plain(x.get("name") or x.get("city"))) or None
        if any(x.get("isRemote") for x in locs):loc=("Remote | "+loc) if loc else "Remote"
        job=row.get("job") or {}
        jid=row.get("id") or row.get("extId")
        out.append({"external_id":f"gem:{board}:{jid}","source":"gem","company_key":employer,"title":title,"location":loc,"employment_type":job.get("employmentType"),"url":f"https://jobs.gem.com/{board}/{jid}","description":"","updated_at":None})
    print(f"Gem / {board}: {len(rows)} live postings, {len(out)} DE candidates",flush=True)
    return out
