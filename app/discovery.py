from __future__ import annotations

"""Production discovery entry point.

The implementation lives in :mod:`app.discovery_impl`.  This wrapper keeps
source-health history advisory-only and removes the implicit discovery-portal
250-detail ceiling without duplicating the large orchestration module.
"""

import json
import tempfile
from pathlib import Path

from app.discovery_impl import *  # re-export provider constants used elsewhere
from app.discovery_impl import discover as _discover_impl


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

    Discovery portals are exhaustive by default.  An explicit configured
    ``max_detail_pages`` value is still honored as an emergency safeguard.
    """
    runtime_config=dict(config)
    runtime_config["discovery_portal"]=[]
    for source in config.get("discovery_portal", []):
        row=dict(source)
        # Presence with None is intentional: discovery_impl uses dict.get with a
        # legacy fallback of 250, while an explicit None means no detail ceiling.
        row.setdefault("max_detail_pages", None)
        runtime_config["discovery_portal"].append(row)

    # discovery_impl's historical health reader can quarantine sources.  Give it
    # a fresh, existing report so no prior failures suppress this production run.
    # After execution, publish the newly generated health report to the normal
    # state path for dashboards, diagnostics, and the next run's observability.
    target=Path(health_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="job-discovery-health-") as tmpdir:
        run_health=Path(tmpdir)/"source_health.json"
        run_health.write_text(json.dumps({"sources": []}), encoding="utf-8")
        result=_discover_impl(
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
