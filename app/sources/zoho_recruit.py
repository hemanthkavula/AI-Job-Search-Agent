from __future__ import annotations

import html
import json
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def _plain(value: str) -> str:
    value=re.sub(r"(?is)<(?:script|style)[^>]*>.*?</(?:script|style)>"," ",str(value or ""))
    value=re.sub(r"(?i)<br\s*/?>|</(?:p|li|div|h[1-6])>","\n",value)
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",value))).strip()


def _decode_js_literal(raw: str) -> str:
    """Decode the JS single-quoted literal around Zoho's JSON.parse(jobs).

    Unlike replacing every \\x22, this respects nested \\\\ quote escapes
    in HTML attributes inside the JSON string.
    """
    out=[]
    i=0
    while i<len(raw):
        char=raw[i]
        if char!="\\":
            out.append(char)
            i+=1
            continue
        i+=1
        if i>=len(raw):
            break
        esc=raw[i]
        if esc in ("x","u"):
            width=2 if esc=="x" else 4
            digits=raw[i+1:i+width+1]
            if len(digits)==width and re.fullmatch(r"[0-9A-Fa-f]+",digits):
                out.append(chr(int(digits,16)))
                i+=width+1
                continue
        out.append({"n":"\n","r":"\r","t":"\t","b":"\b","f":"\f"}.get(esc,esc))
        i+=1
    return "".join(out)


def _embedded_jobs(page: str) -> list[dict]:
    # Zoho Recruit often renders an almost blank HTML shell, with exact
    # Posting_Title and Job_Description in a JS-escaped JSON.parse payload.
    match=re.search(r"\bvar\s+jobs\s*=\s*JSON\.parse\('([\s\S]*?)'\);",page or "")
    if not match:
        return []
    try:
        rows=json.loads(_decode_js_literal(match.group(1)))
    except (ValueError,TypeError):
        return []
    return [row for row in rows if isinstance(row,dict)] if isinstance(rows,list) else []


def fetch_job(company: str, url: str, timeout: int=25) -> dict | None:
    """Read one authoritative Zoho Recruit posting from its embedded job data."""
    parsed=urlparse(str(url or ""))
    if not parsed.hostname or ".zohorecruit." not in parsed.hostname.lower():
        return None
    match=re.search(r"/jobs/[^/]+/(\d+)",parsed.path or "",re.I)
    if not match:
        return None
    job_id=match.group(1)
    try:
        req=Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"text/html"})
        with urlopen(req,timeout=timeout) as response:
            page=response.read().decode("utf-8",errors="replace")
    except Exception:
        return None
    rows=_embedded_jobs(page)
    if not rows:
        return None
    row=next((x for x in rows if str(x.get("id") or x.get("Id") or x.get("Job_ID") or "")==job_id),None)
    if row is None and len(rows)==1:
        row=rows[0]
    if not row:
        return None
    title=_plain(row.get("Posting_Title") or row.get("Job_Title") or row.get("title") or "")
    description=_plain(row.get("Job_Description") or row.get("Description") or "")
    if not title or len(description)<180:
        return None
    m=re.search(r"""(?is)<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"']+)["']""",page)
    employer=_plain(m.group(1)) if m else (company or parsed.hostname.split(".")[0])
    location=", ".join(str(x) for x in (row.get("City"),row.get("State"),row.get("Country")) if x)
    return {
        "external_id":f"zoho_recruit:{parsed.hostname}:{job_id}",
        "source":"zoho_recruit",
        "company_key":employer,
        "company":employer,
        "title":title,
        "location":location or None,
        "url":url,
        "original_url":url,
        "ats_provider":"zoho_recruit",
        "ats_identifier":parsed.hostname.split(".")[0],
        "job_id":job_id,
        "requisition_id":job_id,
        "description":description,
        "description_complete":True,
        "exact_job_metadata_source":"zoho_recruit_embedded_exact_detail",
    }
