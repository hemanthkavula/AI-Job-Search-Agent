from __future__ import annotations

import argparse
import os
import shutil
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "generated"

def reset(apply: bool = False) -> list[str]:
    """Remove all runtime/generated state while preserving source, config, and candidate inputs."""
    targets: list[str] = []
    if GENERATED.exists():
        targets.append(str(GENERATED.relative_to(ROOT)))
    if apply and GENERATED.exists():
        # Windows/OneDrive can leave generated artifacts read-only. Clear those
        # attributes before deletion, then retry any failing remove operation.
        for item in GENERATED.rglob("*"):
            try:
                os.chmod(item, stat.S_IWRITE)
            except OSError:
                pass
        try:
            os.chmod(GENERATED, stat.S_IWRITE)
        except OSError:
            pass

        def _remove_readonly(func, path, exc_info):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except OSError:
                raise exc_info[1]

        try:
            shutil.rmtree(GENERATED, onexc=_remove_readonly)
        except TypeError:
            shutil.rmtree(GENERATED, onerror=_remove_readonly)
        GENERATED.mkdir(parents=True, exist_ok=True)
    return targets

def main():
    p = argparse.ArgumentParser(description="Reset all generated job-agent runtime state for a clean end-to-end run.")
    p.add_argument("--apply", action="store_true", help="Actually delete generated/ and recreate it empty.")
    args = p.parse_args()
    targets = reset(args.apply)
    print(("Reset" if args.apply else "Would reset") + f" {len(targets)} runtime location(s):")
    for item in targets:
        print(f" - {item}")
    if not args.apply:
        print("Dry run only. Re-run with --apply to perform the reset.")
    else:
        print("Fresh state ready: generated/ is empty.")
        print("Preserved: source code, tests, candidate profile, job source configuration, and master input documents.")

if __name__ == "__main__":
    main()
