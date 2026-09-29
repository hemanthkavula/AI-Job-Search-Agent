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
    # SuccessFactors search is lexical. Use several broad DE-family queries for
    # recall, then let the downstream semantic classifier make the final family
    # decision from title + official JD.
    queries=("data engineer","data platform","data infrastructure","data pipeline","etl","big data","analytics engineer")
    out=[]; seen=set()
    family_terms=("data engineer","data engineering","data platform","data infrastructure","data pipeline","etl","big data","analytics engineer")
    for query_text in queries:
        query=urlencode({"q":query_text,"locationsearch":"United States"})
        search_url=urljoin(base_url.rstrip("/")+"/","search/")+"?"+query
        try:
            body=_get(search_url,timeout)
        except Exception:
            continue
        hrefs=re.findall(r'href=["\']([^"\']*(?:/job/)[^"\']+)["\']',body,re.I)
        for href in hrefs:
            url=urljoin(base_url,html.unescape(href))
            if url in seen:continue
            seen.add(url)
            try:detail=_get(url,timeout)
            except Exception:continue
            text=_plain(detail)
            title_match=re.search(r"<title>(.*?)</title>",detail,re.I|re.S)
            title=_plain(title_match.group(1)) if title_match else ""
            hay=(title+" "+text[:3500]).lower()
            if not any(term in hay for term in family_terms):continue
            out.append({
                "external_id":f"successfactors:{company}:{url}",
                "source":"successfactors","company_key":company,
                "title":title or "Data Engineering role","location":None,
                "url":url,"original_url":url,"ats_provider":"successfactors",
                "ats_identifier":base_url,"description":text,
                "description_complete":bool(text),"updated_at":None,
            })
    print(f"SuccessFactors / {company}: {len(out)} DE-family jobs",flush=True)
    return out
