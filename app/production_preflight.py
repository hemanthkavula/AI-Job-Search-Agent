from __future__ import annotations

import argparse
import inspect
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import load_profile
from app.discovery import ALL_ATS_PROVIDERS
from app.filters import passes_hard_filters, title_is_target
from app.scheduled_runner import RUN_SLOTS, RUN_WEEKDAYS, SLOT_RECOVERY_MINUTES

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HEALTH_PATH = ROOT / "state" / "source_health.json"
DEFAULT_SOURCE_CONFIG = ROOT / "data" / "job_sources.json"

BAD_EFFECTIVE_STATUSES = {
    "no_crawlable_links",
    "blocked_or_http_error",
    "unreachable",
    "broken",
    "invalid_pattern",
}

REQUIRED_TARGET_ROLES = (
    "Data Engineer",
    "Senior Data Engineer",
    "Analytics Engineer",
    "Data Platform Engineer",
    "Data Infrastructure Engineer",
    "Data Pipeline Engineer",
    "Data Warehouse Engineer",
    "ETL Engineer",
    "Big Data Engineer",
)

REQUIRED_ATS_FAMILIES = {
    "workday",
    "greenhouse",
    "lever",
    "smartrecruiters",
    "ashby",
    "bamboohr",
    "breezyhr",
    "jobvite",
    "icims",
    "oracle",
    "ukg",
    "firststage",
    "freshteam",
    "jobscore",
    "peopleadmin",
    "recruitee",
    "applicantstack",
    "kula",
}

EXPECTED_SLOTS = ((7, 30), (10, 0), (12, 30), (15, 30), (18, 30), (21, 0))


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _effective_status(row: dict) -> str:
    existing = str(row.get("effective_status") or "").strip().lower()
    if existing:
        return existing
    status = str(row.get("status") or "").strip().upper()
    error = str(row.get("error") or "").lower()
    if status == "OK":
        return "ok"
    if "no crawlable" in error:
        return "no_crawlable_links"
    if "invalid pattern" in error or "invalid regex" in error:
        return "invalid_pattern"
    if any(token in error for token in ("403", "429", "access denied", "blocked", "forbidden", "captcha")):
        return "blocked_or_http_error"
    if any(token in error for token in ("404", "410", "not found", "gone")):
        return "broken"
    if any(token in error for token in ("timeout", "timed out", "unreachable", "connection reset", "connection refused", "dns")):
        return "unreachable"
    # Unknown adapter failures remain retryable every production recovery attempt;
    # only well-understood persistent failures are quarantined for the bounded TTL.
    if status == "ERROR":
        return "transient_error"
    if status == "SKIPPED_UNHEALTHY":
        return "skipped_unhealthy"
    return status.lower() or "unknown"


def _health_rows(payload) -> list[dict]:
    rows = []
    if isinstance(payload, list):
        rows.extend(x for x in payload if isinstance(x, dict))
        return rows
    if not isinstance(payload, dict):
        return rows
    embedded = payload.get("sources")
    if isinstance(embedded, list):
        rows.extend(x for x in embedded if isinstance(x, dict))
    # Discovery persists runtime health as a keyed dictionary. Keep supporting
    # that format and convert it into the legacy/report shape discovery reads.
    for key, value in payload.items():
        if key == "sources" or not isinstance(value, dict):
            continue
        if value.get("source") or value.get("provider"):
            rows.append(value)
    return rows


def normalize_source_health(path=DEFAULT_HEALTH_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        return {"path": str(path), "exists": False, "rows": 0, "quarantined": 0, "changed": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"path": str(path), "exists": True, "rows": 0, "quarantined": 0, "changed": False, "error": str(exc)}

    merged: dict[tuple[str, str], dict] = {}
    for source_row in _health_rows(payload):
        row = dict(source_row)
        provider = str(row.get("provider") or row.get("source") or "").strip()
        company = str(row.get("company") or provider).strip()
        if not provider:
            continue
        row["provider"] = provider
        row["source"] = provider
        candidate_effective = _effective_status(row)
        key = (provider, company)
        previous = merged.get(key)
        candidate_time = _parse_time(row.get("checked_at")) or datetime.min.replace(tzinfo=timezone.utc)
        previous_time = (_parse_time(previous.get("checked_at")) if previous else None) or datetime.min.replace(tzinfo=timezone.utc)

        # A SKIPPED_UNHEALTHY row is evidence that quarantine was honored, not
        # evidence that the underlying source recovered. Preserve the prior known
        # persistent failure classification until a later real adapter attempt is OK.
        if previous and candidate_effective == "skipped_unhealthy" and previous.get("effective_status") in BAD_EFFECTIVE_STATUSES:
            row["effective_status"] = previous["effective_status"]
        else:
            row["effective_status"] = candidate_effective

        if previous is None or candidate_time >= previous_time:
            merged[key] = row

    rows = sorted(merged.values(), key=lambda r: (str(r.get("provider")), str(r.get("company"))))
    canonical = {
        "format_version": 2,
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "sources": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(canonical, indent=2), encoding="utf-8")
    return {
        "path": str(path),
        "exists": True,
        "rows": len(rows),
        "quarantined": sum(r.get("effective_status") in BAD_EFFECTIVE_STATUSES for r in rows),
        "changed": payload != canonical,
    }


def _synthetic_job(title: str, description: str | None = None) -> dict:
    description = description or (
        "Build production data pipelines and ETL/ELT workflows using Python, SQL, Spark, Airflow, "
        "Snowflake, data modeling, data ingestion, and data transformation. Full-time position."
    )
    return {
        "company_key": "Example Employer",
        "title": title,
        "location": "New York, NY, United States",
        "employment_type": "Full-Time",
        "description": description,
    }


def validate_requirements(source_config=DEFAULT_SOURCE_CONFIG) -> dict:
    failures = []
    warnings = []
    profile = load_profile()
    configured_roles = list(profile.get("preferences", {}).get("target_roles") or [])

    if tuple(RUN_SLOTS) != EXPECTED_SLOTS:
        failures.append(f"scheduler slots drifted: {RUN_SLOTS}")
    if set(RUN_WEEKDAYS) != {0, 1, 2, 3, 4}:
        failures.append(f"scheduler weekdays drifted: {RUN_WEEKDAYS}")
    if int(SLOT_RECOVERY_MINUTES) != 55:
        failures.append(f"scheduler recovery window drifted: {SLOT_RECOVERY_MINUTES}")

    for title in REQUIRED_TARGET_ROLES:
        job = _synthetic_job(title)
        if not title_is_target(title, job["description"]):
            failures.append(f"required target title is not accepted: {title}")
        ok, reasons = passes_hard_filters(job, profile)
        if not ok:
            failures.append(f"required target title fails hard filters: {title}: {reasons}")

    normalized_roles = {re.sub(r"\s+", " ", x.strip().lower()) for x in configured_roles}
    missing_profile_roles = [r for r in REQUIRED_TARGET_ROLES[:6] if r.lower() not in normalized_roles]
    if missing_profile_roles:
        warnings.append("profile target_roles will be runtime-augmented for: " + ", ".join(missing_profile_roles))

    foreign = _synthetic_job("Senior Data Engineer")
    foreign["location"] = "Bangalore, India"
    ok, _ = passes_hard_filters(foreign, profile)
    if ok:
        failures.append("non-US job passed hard filters")

    no_sponsor = _synthetic_job(
        "Senior Data Engineer",
        "Build Python SQL Spark data pipelines, ETL, data warehouse and data modeling. Full-time. "
        "Candidates must be authorized to work without current or future visa sponsorship.",
    )
    ok, _ = passes_hard_filters(no_sponsor, profile)
    if ok:
        failures.append("explicit no-future-sponsorship job passed hard filters")

    hard_filter_source = inspect.getsource(passes_hard_filters)
    if "target_company" in hard_filter_source or "target company" in hard_filter_source.lower():
        failures.append("target-company annotation leaked into hard eligibility filtering")

    supported = set(ALL_ATS_PROVIDERS)
    missing_families = sorted(REQUIRED_ATS_FAMILIES - supported)
    if missing_families:
        failures.append("required ATS families missing from discovery architecture: " + ", ".join(missing_families))

    source_config = Path(source_config)
    try:
        sources = json.loads(source_config.read_text(encoding="utf-8"))
    except Exception as exc:
        failures.append(f"job source configuration cannot be loaded: {exc}")
        sources = {}
    policy = (sources.get("discovery_portals") or {}).get("policy")
    if policy != "discovery_only_resolve_to_authoritative_employer_posting":
        failures.append(f"discovery portal authority policy drifted: {policy!r}")

    master = profile.get("master_resume_reference") or {}
    counts = master.get("bullet_counts") or {}
    if master.get("layout_version") != "master-2026-10-03":
        failures.append("master resume layout version is missing or changed")
    if counts != {"Fidelity Investments": 10, "Cigna Healthcare": 8, "Target Corporation": 8}:
        failures.append(f"master resume bullet contract drifted: {counts}")

    return {
        "passed": not failures,
        "failures": failures,
        "warnings": warnings,
        "scheduler_slots": [list(x) for x in RUN_SLOTS],
        "ats_families_supported": len(supported),
        "profile_target_roles": configured_roles,
        "required_target_roles": list(REQUIRED_TARGET_ROLES),
        "master_layout_version": master.get("layout_version"),
    }


def run(strict=False, normalize_health=True) -> dict:
    health = normalize_source_health() if normalize_health else {"skipped": True}
    requirements = validate_requirements()
    result = {"source_health": health, "requirements": requirements}
    print(json.dumps(result, indent=2))
    if strict and not requirements["passed"]:
        raise SystemExit("Production preflight failed: " + " | ".join(requirements["failures"]))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalize persistent source health and validate production requirements.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if a production requirement has drifted.")
    parser.add_argument("--check-only", action="store_true", help="Validate requirements without changing source-health state.")
    args = parser.parse_args()
    run(strict=args.strict, normalize_health=not args.check_only)
