from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen


def _plain(value: str) -> str:
    s=html.unescape(str(value or "").replace(r"\:",":"))
    s=re.sub(r"(?i)</(?:p|li|div|h[1-6])>|<br\s*/?>","\n",s)
    s=re.sub(r"(?is)<[^>]+>"," ",s)
    return re.sub(r"\s+"," ",html.unescape(s)).strip()


def _exact_payload(page: str, job_id: str) -> str:
    """Decode Taleo's !*!-separated, URL-encoded requisition description.

    A Taleo detail page can contain a complete job in its client state even
    when visible HTML exposes only a generic recruiter/footer shell.
    """
    if not job_id or job_id not in page:
        return ""
    candidates=[]
    # A literal !*! marker precedes escaped HTML in Taleo's page state.
    for m in re.finditer(r"!\*!(%3C[^\r\n]*?)(?=!\|!|!\*|[<\r\n])",page,re.I):
        payload=unquote(m.group(1))
        desc=_plain(payload)
        if len(desc)>180 and any(x in desc.lower() for x in ("skill","experience","responsibilit","requirement","qualification")):
            candidates.append(desc)
    return max(candidates,key=len,default="")


def fetch_job(company: str, url: str, timeout: int=25) -> dict | None:
    parsed=urlparse(str(url or ""))
    if not parsed.hostname or "taleo.net" not in parsed.hostname.lower():
        return None
    job_id=(parse_qs(parsed.query).get("job") or [""])[0]
    if not job_id:
        return None
    try:
        req=Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"text/html"})
        with urlopen(req,timeout=timeout) as response:
            page=response.read().decode("utf-8","replace")
    except Exception:
        return None
    desc=_exact_payload(page,job_id)
    if not desc:
        return None
    title_match=re.search(r"""(?is)<meta[^>]+(?:property=["']og:title["'][^>]*content=["']([^"']+)|content=["']([^"']+)["'][^>]*property=["']og:title["'])""",page)
    title=_plain((title_match.group(1) or title_match.group(2)) if title_match else "")
    tenant=parsed.hostname.split(".")[0]
    # Taleo tenant prefixes such as tas- are infrastructure, not employer names.\n    employer=re.sub(r"(?i)^(?:tas-|recruiting-|career-)", "", tenant).replace("-", " ").title()\n    if not employer:\n        employer=company or tenant
    return {
        "external_id":f"taleo:{tenant}:{job_id}",
        "source":"taleo",
        "company_key":employer,
        "company":employer,
        "title":title,
        "url":url,
        "original_url":url,
        "ats_provider":"taleo",
        "ats_identifier":tenant,
        "job_id":job_id,
        "requisition_id":job_id,
        "description":desc,
        "description_complete":True,
        "exact_job_metadata_source":"taleo_embedded_exact_detail",
    }
