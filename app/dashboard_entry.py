from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import uvicorn

from app.dashboard import STATE_DIR, app


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


@app.on_event("startup")
def cleanup_dashboard_persistent_state() -> None:
    """Keep Railway dashboard state bounded without deleting dashboard history.

    Production/debug discovery snapshots (*_eligible.json and *_finalized.json)
    can be hundreds of MB and are retained in GitHub run artifacts. The hosted
    dashboard only needs cycle summaries, manifests/application queues, the
    ledger and generated resume artifacts.
    """
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
