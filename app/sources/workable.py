from __future__ import annotations
import html
import json
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.sources.career_site import _workable_public


def _plain(value) -> str:
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",html.unescape(str(value or "")))).strip()


def fetch_jobs(company: str, search_url: str, timeout: int=25) -> list[dict]:
    """Collect Workable jobs through its public account feed."""
    return _workable_public(company,search_url,timeout)


def fetch_job(company: str, url: str, timeout: int=25) -> dict | None:
    """Resolve one exact Workable job from the public account widget API."""
    parsed=urlparse(str(url or ""))
    parts=[x for x in parsed.path.split("/") if x]
    slug=""
    shortcode=""
    # Supported public shapes:
    #   /<account>/j/<shortcode>
    #   /j/<shortcode> (when account is known only from the supplied company URL)
    if len(parts)>=3 and parts[-2].lower()=="j":
        shortcode=parts[-1]
        if parts[0].lower()!="j":
            slug=parts[0]
    if not slug:
        m=re.search(r"apply\.workable\.com/([^/?#]+)/j/([^/?#]+)",str(url or ""),re.I)
        if m:
            slug,shortcode=m.group(1),m.group(2)
    if not slug or not shortcode:
        return None

    api=f"https://www.workable.com/api/accounts/{slug}?details=true"
    try:
        req=Request(api,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
        with urlopen(req,timeout=timeout) as resp:
            payload=json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    account_name=str(payload.get("name") or "").strip()
    for j in payload.get("jobs") or []:
        if not isinstance(j,dict):
            continue
        candidate_ids={str(j.get("shortcode") or ""),str(j.get("code") or "")}
        candidate_url=str(j.get("url") or j.get("shortlink") or "")
        if shortcode not in candidate_ids and shortcode not in candidate_url:
            continue
        desc=_plain(j.get("description") or j.get("full_description") or "")
        title=str(j.get("title") or "").strip()
        department=str(j.get("department") or "").strip()
        resolved_company=company or account_name or slug
        # Recruiting-marketplace boards can carry the actual employer in the
        # department field. Use it only when the description explicitly names it
        # up front, which is stronger evidence than the generic board account.
        if department and re.search(rf"(?i)\b(?:about\s+)?{re.escape(department)}\b",desc[:900]):
            resolved_company=department
        loc=", ".join(str(x) for x in (j.get("city"),j.get("state"),j.get("country")) if x)
        canonical=str(j.get("url") or f"https://apply.workable.com/{slug}/j/{shortcode}")
        return {
            "external_id":f"workable:{slug}:{shortcode}",
            "source":"workable",
            "company_key":resolved_company,
            "company":resolved_company,
            "title":title,
            "location":loc or None,
            "employment_type":j.get("employment_type"),
            "url":canonical,
            "original_url":canonical,
            "ats_provider":"workable",
            "ats_identifier":slug,
            "job_id":shortcode,
            "requisition_id":shortcode,
            "description":desc,
            "description_complete":bool(desc),
            "posted_at":j.get("published_on") or j.get("published"),
            "exact_job_metadata_source":"workable_public_account_api",
        }
    return None
