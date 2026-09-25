from __future__ import annotations
from app.sources.career_site import _workable_public

def fetch_jobs(company: str, search_url: str, timeout: int=25) -> list[dict]:
    """Collect Workable jobs through its public account feed."""
    return _workable_public(company,search_url,timeout)
