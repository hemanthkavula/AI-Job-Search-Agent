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


def fetch_jobs(company: str, base_url: str, timeout: int = 20, max_pages: int | None = None) -> list[dict]:
    """Traverse public SuccessFactors search pages broadly.

    Discovery intentionally does not decide whether a posting is Data
    Engineering-family. That decision belongs to the shared downstream
    classifier after the official detail page has been collected.
    """
    out=[];seen_jobs=set();seen_pages=set();queue=[];truncated=False;pages=0
    # Start with an unrestricted search. Keep United States as a discovery hint
    # because this project only targets U.S. jobs; pagination links discovered
    # from the provider are followed as returned.
    first=urljoin(base_url.rstrip("/")+"/","search/")+"?"+urlencode({"locationsearch":"United States"})
    queue.append(first)
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
        # Follow provider search/pagination links instead of assuming one page.
        for href in re.findall(r'href=["\']([^"\']+)["\']',body,re.I):
            u=urljoin(search_url,html.unescape(href));lo=u.lower()
            if "/search/" in lo and u not in seen_pages and u not in queue:
                queue.append(u)
    state="TRUNCATED" if truncated else "EXHAUSTED_OR_LINK_FRONTIER"
    print(f"SuccessFactors / {company}: {len(out)} jobs from {pages} search pages, pagination={state}",flush=True)
    return out
