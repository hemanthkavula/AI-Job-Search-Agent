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


@app.on_event("startup")
def cleanup_dashboard_persistent_state() -> None:
    """Remove discovery-only state that older dashboard syncs persisted by mistake."""
    state_dir = Path(STATE_DIR)
    state_dir.mkdir(parents=True, exist_ok=True)

    removed = []
    for name in ("seen_jobs.json",):
        path = state_dir / name
        if path.exists() and path.is_file():
            size = path.stat().st_size
            path.unlink()
            removed.append({"name": name, "bytes": size})

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

    print(
        "Dashboard mounted-volume cleanup: "
        f"removed={removed or 'none'}; free_bytes={free_bytes}; total_bytes={total_bytes}; "
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
