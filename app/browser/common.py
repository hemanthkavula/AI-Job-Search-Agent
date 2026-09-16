from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class FillResult:
    field: str
    status: str
    detail: str | None = None

SENSITIVE_PATTERNS = (
    "sponsor", "authorization", "authorized to work", "salary", "compensation",
    "relocate", "gender", "race", "ethnicity", "disability", "veteran",
    "criminal", "background", "attest", "signature"
)

def is_sensitive(label: str) -> bool:
    value=(label or "").lower()
    return any(p in value for p in SENSITIVE_PATTERNS)

async def fill_first(page: Any, selectors: list[str], value: str, field: str) -> FillResult:
    for selector in selectors:
        loc=page.locator(selector)
        if await loc.count():
            try:
                await loc.first.fill(value)
                return FillResult(field,"filled",selector)
            except Exception:
                continue
    return FillResult(field,"not_found")
