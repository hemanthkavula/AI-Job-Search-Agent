from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import time
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

        def _try_remove_tree():
            try:
                shutil.rmtree(GENERATED, onexc=_remove_readonly)
            except TypeError:
                shutil.rmtree(GENERATED, onerror=_remove_readonly)

        try:
            _try_remove_tree()
        except PermissionError as exc:
            # WinError 32 means another process still has a generated artifact
            # open (commonly Word/LibreOffice or OneDrive). Stop only known
            # document/PDF helper processes, then retry a few times.
            if getattr(exc, "winerror", None) != 32:
                raise
            for image in ("WINWORD.EXE", "soffice.exe", "soffice.bin", "AcroRd32.exe"):
                subprocess.run(
                    ["taskkill", "/F", "/IM", image],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            last = exc
            for _ in range(5):
                time.sleep(1)
                try:
                    _try_remove_tree()
                    last = None
                    break
                except PermissionError as retry_exc:
                    last = retry_exc
            if last is not None:
                raise RuntimeError(
                    "A generated file is still open in another process. Close any "
                    "Word/LibreOffice/PDF windows and pause OneDrive syncing for this "
                    "project, then rerun the reset."
                ) from last

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
