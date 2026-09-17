from __future__ import annotations
import json
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.request import Request, urlopen

DE_TITLE_PATTERNS = (
    "data engineer",
    "data platform engineer",
    "data infrastructure engineer",
    "data pipeline engineer",
    "big data engineer",
    "cloud data engineer",
    "aws data engineer",
    "azure data engineer",
)


def _json(url: str, timeout: int = 12, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = Request(url, data=data, headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": "en-US",
        "User-Agent": "AI-Job-Search-Agent/0.5",
    })
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _plain(value: str | None) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_de_title(title: str | None) -> bool:
    value = re.sub(r"\s+", " ", (title or "").lower()).strip()
    return any(x in value for x in DE_TITLE_PATTERNS)


def _posted_at(value: str | None) -> str | None:
    """Convert Workday's English relative postedOn value to an approximate UTC timestamp."""
    text = (value or "").strip().lower()
    now = datetime.now(timezone.utc)
    if text in {"posted today", "today"}:
        return now.isoformat()
    if text in {"posted yesterday", "yesterday"}:
        return (now - timedelta(days=1)).isoformat()
    match = re.search(r"posted\s+(\d+)\s+days?\s+ago", text)
    if match:
        return (now - timedelta(days=int(match.group(1)))).isoformat()
    return None


def fetch_jobs(company: str, host: str, tenant: str, site: str, locale: str = "en-US", timeout: int = 12) -> list[dict]:
    """Fetch Data Engineer-family jobs from one public Workday CXS career site.

    Workday's listing endpoint is limited to 20 rows. We scan listing metadata first
    and only request full details for plausible Data Engineer titles, keeping hourly
    discovery inexpensive even for very large enterprise boards.
    """
    origin = f"https://{host.strip('/')}"
    base = f"{origin}/wday/cxs/{tenant}/{site}"
    offset = 0
    limit = 20
    total: int | None = None
    listing_count = 0
    candidate_count = 0
    out: list[dict] = []

    while True:
        payload = _json(f"{base}/jobs", timeout, {
            "appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""
        })
        if total is None:
            try: total = int(payload.get("total") or 0)
            except Exception: total = 0
        rows = payload.get("jobPostings") or []
        if not rows:
            break
        listing_count += len(rows)

        for row in rows:
            if not _is_de_title(row.get("title")):
                continue
            candidate_count += 1
            external_path = row.get("externalPath") or ""
            if not external_path:
                continue
            try:
                detail_payload = _json(f"{base}{external_path}", timeout)
                detail = detail_payload.get("jobPostingInfo") or detail_payload
            except Exception:
                detail = {}

            req_id = detail.get("jobReqId") or detail.get("jobPostingId") or external_path.rsplit("_", 1)[-1]
            title = detail.get("title") or row.get("title") or ""
            location = detail.get("location") or row.get("locationsText")
            additional = detail.get("additionalLocations") or []
            if additional:
                location = " | ".join([location] + [str(x) for x in additional if x]) if location else " | ".join(map(str, additional))
            public_url = f"{origin}/{locale}/{site}{external_path}"
            out.append({
                "external_id": f"workday:{tenant}:{site}:{req_id}",
                "source": "workday",
                "company_key": company,
                "title": title,
                "location": location,
                "employment_type": detail.get("timeType"),
                "url": public_url,
                "description": _plain(detail.get("jobDescription")),
                "updated_at": _posted_at(row.get("postedOn")),
                "posted_on": row.get("postedOn"),
            })

        offset += len(rows)
        if len(rows) < limit or (total and offset >= total):
            break

    print(f"Workday / {company}: {listing_count} listings, {candidate_count} DE candidates, {len(out)} detailed JDs", flush=True)
    return out
