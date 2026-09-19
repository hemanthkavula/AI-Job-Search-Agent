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


def fetch_jobs(company: str, base_url: str, timeout: int = 20) -> list[dict]:
    query = urlencode({"q": "data engineer", "locationsearch": "United States"})
    search_url = urljoin(base_url.rstrip("/") + "/", "search/") + "?" + query
    body = _get(search_url, timeout)
    hrefs = re.findall('href="([^"]+/job/[^"]+)"', body, re.I)
    out = []
    seen = set()
    for href in hrefs:
        url = urljoin(base_url, html.unescape(href))
        if url in seen:
            continue
        seen.add(url)
        try:
            detail = _get(url, timeout)
        except Exception:
            continue
        text = _plain(detail)
        title_match = re.search(r"<title>(.*?)</title>", detail, re.I | re.S)
        title = _plain(title_match.group(1)) if title_match else "Data Engineer"
        if "data engineer" not in title.lower():
            continue
        out.append({
            "external_id": f"successfactors:{company}:{url}",
            "source": "successfactors",
            "company_key": company,
            "title": title,
            "location": None,
            "url": url,
            "original_url": url,
            "ats_provider": "successfactors",
            "ats_identifier": base_url,
            "description": text,
            "description_complete": bool(text),
            "updated_at": None,
        })
    print(f"SuccessFactors / {company}: {len(out)} DE jobs", flush=True)
    return out
