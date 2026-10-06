from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from urllib.parse import quote

import uvicorn

import app.dashboard as dashboard
from app.job_identity import identity_keys

STATE_DIR = dashboard.STATE_DIR
app = dashboard.app
_ORIGINAL_JOBS = dashboard._jobs
_HISTORY_CACHE: dict = {"signature": None, "rows": []}


def _path_size(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    if path.is_dir():
        for child in path.rglob("*"):
            if child.is_file():
                try:
                    total += child.stat().st_size
                except OSError:
                    pass
    return total


def _remove_file(path: Path, removed: list[dict]) -> None:
    if not path.exists() or not path.is_file():
        return
    try:
        size = path.stat().st_size
        path.unlink()
        removed.append({"name": str(path.relative_to(STATE_DIR)), "bytes": size})
    except OSError as exc:
        print(f"WARNING: dashboard storage cleanup could not remove {path}: {exc}")


def _history_signature() -> tuple:
    """Cheap change detector for the files that feed the dashboard application list."""
    paths = [dashboard.LEDGER, dashboard.CONFIRMED, dashboard.HIDDEN]
    cycles = dashboard.CYCLES
    if cycles.exists():
        for pattern in ("*_summary.json", "*_manifest.json", "*_application_queue.json"):
            paths.extend(cycles.glob(pattern))
    signature = []
    for path in sorted(paths, key=lambda value: str(value)):
        try:
            stat = path.stat()
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            signature.append((str(path), 0, 0))
    return tuple(signature)


def _history_identities(row: dict) -> list[str]:
    """Return strong aliases used to collapse the same historical job.

    Stored keys can change between pipeline stages (for example an ATS external
    ID versus a canonical requisition key), so we compare every strong alias.
    Requisition IDs and normalized job URLs are safe cross-stage identities.
    Semantic company/title/location keys are used only when no stronger identity
    exists; otherwise they can collapse separate requisitions with the same role.
    """
    identities: list[str] = []
    explicit = str(
        row.get("key")
        or row.get("job_key")
        or row.get("external_id")
        or row.get("job_id")
        or ""
    ).strip()
    if explicit:
        identities.append(f"key:{explicit}")

    aliases: list[str] = []
    try:
        aliases = identity_keys(row)
    except Exception:
        aliases = []

    strong = [alias for alias in aliases if alias.startswith(("req:", "url:"))]
    identities.extend(strong)
    if not strong and not explicit:
        semantic = [alias for alias in aliases if alias.startswith("semantic:")]
        identities.extend(semantic)
        if not semantic:
            company = str(row.get("company") or row.get("company_name") or "").strip().lower()
            title = str(row.get("title") or row.get("job_title") or "").strip().lower()
            if company or title:
                identities.append(f"name:{company}|{title}")
    return list(dict.fromkeys(identity for identity in identities if identity))


def _build_jobs_with_history() -> list[dict]:
    """Build current jobs plus preserved historical dashboard application rows."""
    current = list(_ORIGINAL_JOBS())
    hidden = dashboard._hidden_keys()
    ledger = dashboard._json(dashboard.LEDGER, {"jobs": {}})
    ledger_jobs = ledger.get("jobs") or {}
    runs = dashboard._pipeline_runs()
    _, confirmed = dashboard._confirmed_map()

    out: list[dict] = []
    seen: set[str] = set()

    def add(item: dict, identity_row: dict | None = None) -> None:
        identities = _history_identities(identity_row or item)
        if identities and any(identity in seen for identity in identities):
            return
        explicit_key = str(item.get("key") or "")
        if explicit_key and explicit_key in hidden:
            return
        seen.update(identities)
        out.append(item)

    # 1) Live/current operational rows keep their current status and metadata.
    for item in current:
        key = str(item.get("key") or "")
        add(item, ledger_jobs.get(key) or item)

    # 2) Applied history is authoritative even if a later ledger no longer has
    # an active copy of that job.
    for hist in confirmed:
        key = str(hist.get("job_key") or "").strip()
        if not key or key in hidden:
            continue
        ledger_row = ledger_jobs.get(key) or {}
        rp = dashboard._resume_path(ledger_row) or dashboard._resume_path_from_confirmed(hist)
        status = str(hist.get("status") or "SUBMITTED_CONFIRMED")
        submitted_at = hist.get("submitted_at") or ledger_row.get("submitted_at")
        source = ledger_row.get("source") or hist.get("source") or ""
        url = hist.get("url") or ledger_row.get("url") or (ledger_row.get("queue_item") or {}).get("url") or ""
        portal_row = dict(ledger_row)
        portal_row.setdefault("source", source)
        portal_row.setdefault("url", url)
        item = {
            "key": key,
            "company": hist.get("company") or ledger_row.get("company") or "Unknown company",
            "title": hist.get("title") or ledger_row.get("title") or "Unknown role",
            "status": status,
            "stage": dashboard._stage(status),
            "source": source,
            "portal": dashboard._portal(portal_row),
            "url": url,
            "resume": rp.name if rp else None,
            "resume_url": "/resume/" + quote(key, safe="") if rp else None,
            "resume_available": bool(rp),
            "updated": submitted_at or ledger_row.get("last_seen") or ledger_row.get("first_seen"),
            "created": ledger_row.get("first_seen") or submitted_at,
            "location": ledger_row.get("location") or hist.get("location") or "",
            "pipeline": ledger_row.get("cycle_id") or dashboard._pipeline_for(submitted_at, runs),
            "applied_at": submitted_at,
            "reason": hist.get("reason") or ledger_row.get("application_reason") or "",
        }
        add(item, {**ledger_row, **hist, "key": key})

    # 3) Preserve every historical application-ready row from cycle snapshots.
    # Iterate newest first so duplicate identities keep their most recent copy.
    for run in reversed(runs):
        cycle_id = run.get("cycle_id")
        if not cycle_id:
            continue
        for index, row in enumerate(dashboard._cycle_snapshot(cycle_id)):
            if not isinstance(row, dict):
                continue
            stored_key = str(
                row.get("job_key")
                or row.get("key")
                or row.get("external_id")
                or row.get("job_id")
                or ""
            ).strip()
            if stored_key and stored_key in hidden:
                continue
            ledger_row = ledger_jobs.get(stored_key) or {}
            rp = dashboard._resume_path(row) or dashboard._resume_path(ledger_row)
            status = str(row.get("next_action") or "READY_TO_APPLY")
            created = (
                row.get("created")
                or row.get("first_seen")
                or row.get("created_at")
                or run.get("created")
            )
            source = row.get("source") or ledger_row.get("source") or ""
            url = (
                row.get("url")
                or row.get("job_url")
                or row.get("apply_url")
                or ledger_row.get("url")
                or (ledger_row.get("queue_item") or {}).get("url")
                or ""
            )
            display_key = stored_key or f"historical:{cycle_id}:{index}"
            portal_row = dict(ledger_row)
            portal_row.update({"source": source, "url": url})
            item = {
                "key": display_key,
                "company": row.get("company") or row.get("company_name") or ledger_row.get("company") or "Unknown company",
                "title": row.get("title") or row.get("job_title") or ledger_row.get("title") or "Unknown role",
                "status": status,
                "stage": dashboard._stage(status),
                "source": source,
                "portal": dashboard._portal(portal_row),
                "url": url,
                "resume": rp.name if rp else None,
                "resume_url": "/resume/" + quote(stored_key, safe="") if rp and stored_key else None,
                "resume_available": bool(rp),
                "updated": ledger_row.get("last_seen") or created,
                "created": created,
                "location": row.get("location") or ledger_row.get("location") or "",
                "pipeline": cycle_id,
                "applied_at": None,
                "reason": ledger_row.get("application_reason") or "",
            }
            add(item, {**ledger_row, **row, "key": stored_key} if stored_key else row)

    out.sort(
        key=lambda item: item.get("updated") or item.get("applied_at") or item.get("created") or "",
        reverse=True,
    )
    return out


def _jobs_with_history() -> list[dict]:
    """Return cached dashboard rows; rebuild only when backing state changes."""
    signature = _history_signature()
    if _HISTORY_CACHE.get("signature") == signature:
        return _HISTORY_CACHE.get("rows") or []

    rows = _build_jobs_with_history()
    _HISTORY_CACHE["signature"] = _history_signature()
    _HISTORY_CACHE["rows"] = rows
    return rows


# dashboard.py's routes resolve the module-level _jobs symbol at request time, so
# replacing it here repairs All Dates without duplicating or replacing API routes.
dashboard._jobs = _jobs_with_history


@app.on_event("startup")
def cleanup_dashboard_persistent_state() -> None:
    """Keep Railway dashboard state bounded without deleting dashboard history."""
    state_dir = Path(STATE_DIR)
    state_dir.mkdir(parents=True, exist_ok=True)

    removed: list[dict] = []
    _remove_file(state_dir / "seen_jobs.json", removed)

    cycles = state_dir / "cycles"
    if cycles.exists():
        for pattern in ("*_eligible.json", "*_finalized.json"):
            for path in cycles.glob(pattern):
                _remove_file(path, removed)

    storage_breakdown = []
    try:
        for path in sorted(state_dir.iterdir(), key=lambda item: item.name):
            storage_breakdown.append({"name": path.name, "bytes": _path_size(path)})
    except OSError as exc:
        storage_breakdown = [{"error": str(exc)}]

    try:
        usage = shutil.disk_usage(state_dir)
        free_bytes = usage.free
        total_bytes = usage.total
    except OSError:
        free_bytes = None
        total_bytes = None

    removed_bytes = sum(item.get("bytes", 0) for item in removed)
    print(
        "Dashboard mounted-volume cleanup: "
        f"removed_files={len(removed)}; removed_bytes={removed_bytes}; "
        f"free_bytes={free_bytes}; total_bytes={total_bytes}; "
        f"top_level={storage_breakdown}"
    )

    restored = _jobs_with_history()
    stage_counts: dict[str, int] = {}
    for row in restored:
        stage = str(row.get("stage") or "Unknown")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    print(
        "Dashboard history recovery: "
        f"rows={len(restored)}; stages={dict(sorted(stage_counts.items()))}; cache=warm"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
