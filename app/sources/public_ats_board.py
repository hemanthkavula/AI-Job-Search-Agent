from __future__ import annotations
from app.sources.career_site import fetch_jobs as _generic

# Public-board collector for ATS products whose employer boards expose normal
# HTML/JSON-LD job pages. Keeping this adapter separate lets discovery measure
# these ATS families independently and replace individual implementations with
# vendor APIs later without falling back to an unlabelled generic crawl.
def fetch_jobs(company: str, search_url: str, provider: str, job_url_pattern: str = r".+") -> list[dict]:
    rows=_generic(company,search_url,job_url_pattern)
    for row in rows:
        row["source"]=provider
        row["source_family"]="direct_ats_public_board"
        row["ats_provider"]=provider
    return rows
