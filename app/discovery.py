from __future__ import annotations

"""Production discovery entry point.

The implementation lives in :mod:`app.discovery_impl`.  This wrapper keeps
source-health history advisory-only and removes the implicit discovery-portal
250-detail ceiling without duplicating the large orchestration module.

It also enforces the production discovery deadline *inside* source execution.
The legacy implementation waits on futures in submission order and its executor
context waits for every outstanding source before returning.  That meant the
outer workflow timeout could kill the process before downstream filtering,
finalization, persistence, and reporting ran.  The bounded executor below keeps
completed source results, times out unfinished units when the discovery budget
expires, cancels work that has not started, and returns control to the pipeline.

The public module remains a compatibility seam for tests and callers that
monkeypatch provider functions on ``app.discovery``.  Before delegating, those
public bindings are copied into ``discovery_impl`` for the duration of the run.
"""

import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
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


class _DeadlineFuture:
    """Future proxy that applies one shared wall-clock discovery deadline."""

    def __init__(self, future, deadline):
        self._future = future
        self._deadline = deadline

    def result(self, timeout=None):
        if self._deadline is None:
            return self._future.result(timeout=timeout)
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise FutureTimeoutError("production discovery runtime budget exhausted")
        effective = remaining if timeout is None else min(timeout, remaining)
        return self._future.result(timeout=effective)

    def __getattr__(self, name):
        return getattr(self._future, name)


class _DeadlineExecutor(ThreadPoolExecutor):
    """Thread pool that does not block pipeline shutdown after the deadline."""

    deadline = None

    def submit(self, fn, /, *args, **kwargs):
        future = super().submit(fn, *args, **kwargs)
        return _DeadlineFuture(future, self.deadline)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Once the shared deadline is reached, waiting here would recreate the
        # exact 40-minute hang this wrapper is intended to prevent. Running HTTP
        # calls have their own adapter timeouts; queued calls are cancelled.
        expired = self.deadline is not None and time.monotonic() >= self.deadline
        self.shutdown(wait=not expired, cancel_futures=expired)
        return False


def _production_discovery_budget_seconds():
    """Return a safe discovery slice of the total production runtime budget.

    An explicit DISCOVERY_RUNTIME_BUDGET_SECONDS wins. Otherwise, when the
    production cycle supplies PRODUCTION_RUNTIME_BUDGET_SECONDS, reserve time
    for official-JD finalization, resume preparation, queue/state persistence,
    reports, and dashboard sync. Standalone/test discovery remains unbounded.
    """
    explicit = os.getenv("DISCOVERY_RUNTIME_BUDGET_SECONDS")
    if explicit:
        try:
            return max(60, int(explicit))
        except ValueError:
            pass
    total = os.getenv("PRODUCTION_RUNTIME_BUDGET_SECONDS")
    if not total:
        return None
    try:
        total_seconds = max(300, int(total))
    except ValueError:
        return None
    finalization_reserve = max(60, int(os.getenv("PRODUCTION_FINALIZATION_RESERVE_SECONDS", "180")))
    downstream_reserve = max(180, int(os.getenv("PRODUCTION_DOWNSTREAM_RESERVE_SECONDS", "300")))
    # With the current 2100-second production budget this gives discovery 1620s
    # (27 minutes), leaving 8 minutes inside the app plus the workflow's outer
    # guard for finalization/persistence/reporting rather than dying at 40 min.
    return max(60, total_seconds - finalization_reserve - downstream_reserve)


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
    """Run configured sources while guaranteeing production can regain control."""
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

    budget_seconds = _production_discovery_budget_seconds()
    previous_executor = _impl.ThreadPoolExecutor
    if budget_seconds is not None:
        deadline = time.monotonic() + budget_seconds

        class RunDeadlineExecutor(_DeadlineExecutor):
            pass

        RunDeadlineExecutor.deadline = deadline
        _impl.ThreadPoolExecutor = RunDeadlineExecutor
        print(
            f"DISCOVERY DEADLINE enabled: {budget_seconds}s; unfinished source units will be deferred instead of blocking the production cycle.",
            flush=True,
        )

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
        _impl.ThreadPoolExecutor = previous_executor
        # Avoid leaking per-test/per-call patched dependencies into later runs.
        for name, value in previous.items():
            setattr(_impl, name, value)
