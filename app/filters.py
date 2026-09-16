from __future__ import annotations
import re

EXCLUDED_TITLE_TERMS = {
    "analyst", "scientist", "frontend", "front end", "qa engineer",
    "business intelligence", "power bi developer", "tableau developer"
}
EXCLUDED_EMPLOYMENT_TERMS = {"c2c", "corp-to-corp", "corp to corp", "1099 only"}

def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()

def passes_hard_filters(job: dict, profile: dict) -> tuple[bool, list[str]]:
    title=_clean(job.get("title"))
    description=_clean(job.get("description"))
    reasons=[]

    targets=[_clean(x) for x in profile["preferences"]["target_roles"]]
    if not any(t in title or title in t for t in targets):
        # Keep adjacent data-engineering titles for scoring rather than losing good jobs.
        if not ("data" in title and ("engineer" in title or "platform" in title)):
            reasons.append("title outside configured data-engineering targets")

    if any(term in title for term in EXCLUDED_TITLE_TERMS):
        reasons.append("excluded title category")

    combined=f"{title} {description}"
    if any(term in combined for term in EXCLUDED_EMPLOYMENT_TERMS):
        reasons.append("C2C/1099-only language detected")

    return len(reasons) == 0, reasons
