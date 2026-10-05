from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import uvicorn

from app.dashboard import STATE_DIR, app


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

    try:
        usage = shutil.disk_usage(state_dir)
        free_bytes = usage.free
    except OSError:
        free_bytes = None

    print(
        "Dashboard mounted-volume cleanup: "
        f"removed={removed or 'none'}; free_bytes={free_bytes}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
