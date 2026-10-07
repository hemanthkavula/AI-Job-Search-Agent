from __future__ import annotations

from app.jd_finalizer import finalize_report


def finalize_report_by_source(
    report_path,
    output_path="generated/finalized_jobs.json",
    hours=24,
    now=None,
    source_hours=None,
    since=None,
):
    """Finalize against the production window, never a recovery lookback.

    Provider- and tenant-specific watermarks may widen discovery so a
    previously failed source can catch up. They must not widen eligibility or
    resume generation. Every recovered job is re-checked against the same
    production cutoff for the active cycle.

    source_hours remains accepted for API compatibility and diagnostics, but
    is intentionally not used to loosen final freshness.
    """
    return finalize_report(
        report_path,
        output_path,
        hours=hours,
        now=now,
        since=since,
    )
