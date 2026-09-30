from __future__ import annotations

from collections import defaultdict


def _status(row: dict) -> str:
    return str(row.get("status") or "").upper()


def build_source_execution_matrix(source_unit_status: dict, coverage: dict | None = None) -> dict:
    """Summarize every recorded source unit without conflating workflow success with coverage health."""
    coverage = coverage or {}
    providers = defaultdict(lambda: {
        "attempted_units": 0,
        "successful_units": 0,
        "failed_units": 0,
        "skipped_units": 0,
        "zero_result_units": 0,
        "raw_jobs": 0,
    })
    for key, value in (source_unit_status or {}).items():
        if isinstance(value, str):
            source = str(key).split(":", 1)[0]
            row = {"source": source, "status": value, "jobs_returned": 0}
        elif isinstance(value, dict):
            row = value
            source = row.get("source") or str(key).split(":", 1)[0]
        else:
            continue
        if not source:
            continue
        p = providers[source]
        status = _status(row)
        p["attempted_units"] += 1
        jobs = int(row.get("jobs_returned") or 0)
        p["raw_jobs"] += jobs
        if status == "OK":
            p["successful_units"] += 1
            if jobs == 0:
                p["zero_result_units"] += 1
        elif status == "ERROR":
            p["failed_units"] += 1
        elif status == "SKIPPED_UNHEALTHY":
            p["skipped_units"] += 1

    configured = coverage.get("configured_units_by_provider") or {}
    all_names = set(providers) | set(configured)
    result = {}
    for name in sorted(all_names):
        row = dict(providers[name])
        row["configured_units"] = int(configured.get(name) or 0)
        row["unaccounted_configured_units"] = max(
            0, row["configured_units"] - row["attempted_units"]
        )
        result[name] = row
    return result


def evaluate_discovery_health(*, coverage: dict | None, source_matrix: dict,
                              discovered: int, missing_dates: int,
                              healthy_baseline_discovered: int | None = None) -> dict:
    """Return discovery health independently from process/technical success.

    Thresholds are warning signals. They do not impose a fixed market job quota.
    """
    coverage = coverage or {}
    warnings = []
    configured_total = sum(int(v or 0) for v in (coverage.get("configured_units_by_provider") or {}).values())
    attempted_total = sum(v.get("attempted_units", 0) for v in source_matrix.values())
    failed_total = sum(v.get("failed_units", 0) for v in source_matrix.values())
    skipped_total = sum(v.get("skipped_units", 0) for v in source_matrix.values())
    unaccounted_total = sum(v.get("unaccounted_configured_units", 0) for v in source_matrix.values())

    if unaccounted_total:
        warnings.append(f"{unaccounted_total} configured executable source units have no recorded execution outcome")
    if attempted_total and skipped_total / attempted_total > 0.10:
        warnings.append(f"source skip rate is {skipped_total / attempted_total:.1%}")
    if discovered and missing_dates / discovered > 0.35:
        warnings.append(f"unresolved posting-date rate is {missing_dates / discovered:.1%}")
    if healthy_baseline_discovered and healthy_baseline_discovered > 0:
        drop = 1 - (discovered / healthy_baseline_discovered)
        if drop > 0.30:
            warnings.append(f"discovery volume is {drop:.1%} below healthy baseline")

    status = "HEALTHY" if not warnings else "DEGRADED"
    return {
        "status": status,
        "configured_units": configured_total,
        "recorded_units": attempted_total,
        "failed_units": failed_total,
        "skipped_units": skipped_total,
        "unaccounted_configured_units": unaccounted_total,
        "warnings": warnings,
    }
