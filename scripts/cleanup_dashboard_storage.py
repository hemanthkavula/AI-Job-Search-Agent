from __future__ import annotations

import os
import shutil
from pathlib import Path


def main() -> None:
    state_dir = Path(os.getenv("JOB_AGENT_STATE_DIR", "/data/generated"))
    state_dir.mkdir(parents=True, exist_ok=True)

    usage_before = shutil.disk_usage(state_dir)
    removed = []

    # Discovery deduplication state belongs to the GitHub runner/cache, not the
    # hosted dashboard. Older sync logic copied this growing file to Railway and
    # eventually filled the persistent volume.
    for name in ("seen_jobs.json",):
        path = state_dir / name
        if path.exists() and path.is_file():
            size = path.stat().st_size
            path.unlink()
            removed.append((name, size))

    usage_after = shutil.disk_usage(state_dir)
    freed = max(0, usage_after.free - usage_before.free)
    print(
        "Dashboard storage cleanup: "
        f"removed={removed or 'none'}; freed_bytes={freed}; "
        f"free_bytes={usage_after.free}"
    )


if __name__ == "__main__":
    main()
