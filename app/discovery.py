from __future__ import annotations

"""Production discovery entry point.

The implementation lives in :mod:`app.discovery_impl`.  This wrapper keeps
source-health history advisory-only and removes the implicit discovery-portal
250-detail ceiling without duplicating the large orchestration module.

The public module also remains a compatibility seam for tests and callers that
monkeypatch provider functions on ``app.discovery``.  Before delegating, those
public bindings are copied into ``discovery_impl`` for the duration of the run.
"""

import json
import tempfile
from pathlib import Path

from app import discovery_impl as _impl
from app.discovery_impl import *  # re-export provider constants/functions used elsewhere


# Names historically patched through app.discovery. Keep this explicit so a
# wrapper refactor cannot silently turn unit tests into live network calls.
_PATCHABLE_BINDINGS = (
    "greenhouse_jobs", "lever_jobs", "ashby_jobs", "smartrecruiters_jobs",
    "workday_jobs", "dice_jobs", "ziprecruiter_jobs", "monster_jobs",
    "discovery_portal_jobs", "successfactors_jobs", "icims_jobs", "oracle_jobs",
    "career_site_jobs", "eightfold_jobs", "ukg_jobs", "adp_jobs", "avature_jobs",
    "phenom_jobs", "paylocity_jobs", "workable_jobs", "jazzhr_jobs", "dayforce_jobs",
    "gem_jobs", "cornerstone_jobs", "jobvite_jobs", "public_ats_jobs",
    "talentreef_jobs", "load_registry", "save_registry", "learn_from_jobs",
    "as_discovery_config", "load_company_registry", "save_company_registry",
    "learn_companies_from_jobs", "resolve_original_ats", "annotate_jobs",
)


def discover(
    config: dict,
    only_source=None,
    dice_search_terms=None,
    registry_path=None,
    hours=24,
    health_path="state/source_health.json",
    source_hours=None,
    source_unit_hours=None,
    return_coverage=False,
):
    """Run every configured source; retain health as telemetry, never quarantine.

    Discovery portals are exhaustive by default. An explicit configured
    ``max_detail_pages`` value is still honored as an emergency safeguard.
    """
    runtime_config = dict(config)
    runtime_config["discovery_portal"] = []
    for source in config.get("discovery_portal", []):
        row = dict(source)
        # Presence with None is intentional: discovery_impl uses dict.get with a
        # legacy fallback of 250, while explicit None means no detail ceiling.
        row.setdefault("max_detail_pages", None)
        runtime_config["discovery_portal"].append(row)

    # Synchronize the wrapper's public dependency bindings into the implementation
    # so monkeypatching app.discovery continues to isolate network/provider calls.
    previous = {}
    for name in _PATCHABLE_BINDINGS:
        if name in globals() and hasattr(_impl, name):
            previous[name] = getattr(_impl, name)
            setattr(_impl, name, globals()[name])

    target = Path(health_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        # discovery_impl's historical health reader can quarantine sources. Give
        # it a fresh report: health is observability, not a discovery suppressor.
        with tempfile.TemporaryDirectory(prefix="job-discovery-health-") as tmpdir:
            run_health = Path(tmpdir) / "source_health.json"
            run_health.write_text(json.dumps({"sources": []}), encoding="utf-8")
            result = _impl.discover(
                runtime_config,
                only_source,
                dice_search_terms,
                registry_path=registry_path,
                hours=hours,
                health_path=str(run_health),
                source_hours=source_hours,
                source_unit_hours=source_unit_hours,
                return_coverage=return_coverage,
            )
            if run_health.exists():
                target.write_text(run_health.read_text(encoding="utf-8"), encoding="utf-8")
            return result
    finally:
        # Avoid leaking per-test/per-call patched dependencies into later runs.
        for name, value in previous.items():
            setattr(_impl, name, value)
