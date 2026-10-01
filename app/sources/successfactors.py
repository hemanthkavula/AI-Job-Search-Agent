from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlencode
from urllib.request import Request, urlopen


def _get(url: str, timeout: int = 20) -> str:
    request = Request(url, headers={"User-Agent": "AI-Job-Search-Agent/0.5"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def _plain(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub("<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_job_links(base_url: str, body: str) -> list[str]:
    out=[];seen=set()
    for href in re.findall(r'href=["\']([^"\']*(?:/job/)[^"\']+)["\']',body,re.I):
        url=urljoin(base_url,html.unescape(href))
        if url not in seen:
            seen.add(url);out.append(url)
    return out


# SuccessFactors tenants frequently expose only a subset of jobs for a generic
# location search. Seed multiple broad DE-family terms, then deduplicate detail
# URLs. These are discovery hints only: the shared downstream classifier still
# makes the authoritative role-family decision from the collected JD.
SEARCH_TERMS=(
    "",
    "data engineer",
    "data engineering",
    "analytics engineer",
    "data platform",
    "data infrastructure",
    "etl",
    "spark",
    "databricks",
    "data warehouse",
)


def fetch_jobs(company: str, base_url: str, timeout: int = 20, max_pages: int | None = None) -> list[dict]:
    """Traverse public SuccessFactors search pages broadly for U.S. jobs."""
    out=[];seen_jobs=set();seen_pages=set();queue=[];truncated=False;pages=0
    search_root=urljoin(base_url.rstrip("/")+"/","search/")
    for term in SEARCH_TERMS:
        params={"locationsearch":"United States"}
        if term: params["q"]=term
        queue.append(search_root+"?"+urlencode(params))
    while queue:
        if max_pages is not None and pages>=max_pages:
            truncated=True;break
        search_url=queue.pop(0)
        if search_url in seen_pages:continue
        seen_pages.add(search_url)
        try:body=_get(search_url,timeout)
        except Exception:continue
        pages+=1
        for url in _extract_job_links(base_url,body):
            if url in seen_jobs:continue
            seen_jobs.add(url)
            try:detail=_get(url,timeout)
            except Exception:continue
            text=_plain(detail)
            title_match=re.search(r"<title>(.*?)</title>",detail,re.I|re.S)
            title=_plain(title_match.group(1)) if title_match else ""
            out.append({"external_id":f"successfactors:{company}:{url}","source":"successfactors","company_key":company,"title":title,"location":None,"url":url,"original_url":url,"ats_provider":"successfactors","ats_identifier":base_url,"description":text,"description_complete":bool(text),"updated_at":None})
        for href in re.findall(r'href=["\']([^"\']+)["\']',body,re.I):
            u=urljoin(search_url,html.unescape(href));lo=u.lower()
            if "/search/" in lo and u not in seen_pages and u not in queue:
                queue.append(u)
    state="TRUNCATED" if truncated else "EXHAUSTED_OR_LINK_FRONTIER"
    print(f"SuccessFactors / {company}: {len(out)} jobs from {pages} search pages, pagination={state}",flush=True)
    return out
