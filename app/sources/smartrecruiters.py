from __future__ import annotations
import json
import re
from html import unescape
from urllib.request import urlopen, Request
from urllib.parse import urlencode

BASE = "https://api.smartrecruiters.com/v1/companies"

# Keep discovery cheap: only fetch full posting details for plausible Data Engineer roles.
DE_TITLE_PATTERNS = (
    "data engineer",
    "data platform engineer",
    "big data engineer",
    "cloud data engineer",
    "aws data engineer",
    "azure data engineer",
)


def _get_json(url: str, timeout: int) -> dict:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "AI-Job-Search-Agent/0.4"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _plain(value: str | None) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _location(loc: dict) -> str | None:
    parts = [loc.get("city"), loc.get("region"), loc.get("country")]
    value = ", ".join(str(x) for x in parts if x)
    if loc.get("remote"):
        return f"Remote | {value}" if value else "Remote"
    return value or None


def _is_de_title(title: str | None) -> bool:
    value = re.sub(r"\s+", " ", (title or "").lower()).strip()
    return any(pattern in value for pattern in DE_TITLE_PATTERNS)


def fetch_jobs(company_identifier: str, timeout: int = 12) -> list[dict]:
    """Fetch public SmartRecruiters Data Engineer-family postings for one company.

    The listing endpoint is paginated, but detailed posting requests are made only for
    plausible DE titles. This avoids downloading every JD on large company boards.
    """
    out = []
    offset = 0
    limit = 100
    listing_count = 0
    candidate_count = 0

    while True:
        url = f"{BASE}/{company_identifier}/postings?{urlencode({'limit': limit, 'offset': offset})}"
        payload = _get_json(url, timeout)
        rows = payload.get("content") or []
        listing_count += len(rows)

        candidates = [row for row in rows if _is_de_title(row.get("name"))]
        candidate_count += len(candidates)

        for row in candidates:
            posting_id = row.get("uuid") or row.get("id")
            if not posting_id:
                continue
            detail_url = f"{BASE}/{company_identifier}/postings/{posting_id}"
            try:
                detail = _get_json(detail_url, timeout)
            except Exception:
                detail = row

            job_ad = detail.get("jobAd") or {}
            description = " ".join(
                _plain(x) for x in [
                    job_ad.get("companyDescription"),
                    job_ad.get("jobDescription"),
                    job_ad.get("qualifications"),
                    job_ad.get("additionalInformation"),
                ] if x
            )
            company = detail.get("company") or row.get("company") or {}
            loc = detail.get("location") or row.get("location") or {}
            employment = detail.get("typeOfEmployment") or row.get("typeOfEmployment") or {}
            out.append({
                "external_id": f"smartrecruiters:{company_identifier}:{posting_id}",
                "source": "smartrecruiters",
                "company_key": company.get("name") or company_identifier,
                "title": detail.get("name") or row.get("name") or "",
                "location": _location(loc),
                "employment_type": employment.get("label"),
                "url": detail.get("postingUrl") or detail.get("applyUrl") or row.get("ref"),
                "description": description,
                "updated_at": detail.get("releasedDate") or row.get("releasedDate"),
            })

        offset += len(rows)
        total = int(payload.get("totalFound") or 0)
        if not rows or offset >= total:
            break

    print(
        f"SmartRecruiters / {company_identifier}: "
        f"{listing_count} listings, {candidate_count} DE candidates, {len(out)} detailed JDs",
        flush=True,
    )
    return out
