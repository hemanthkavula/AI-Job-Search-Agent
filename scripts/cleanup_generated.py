from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "generated"

# Production memory: never delete these during routine cleanup.
PRESERVE_FILES = {
    "job_ledger.json",
    "scheduler_state.json",
    "seen_jobs.json",
    "discovered_sources.json",
    "source_health.json",
}
PRESERVE_DIRS = {"resumes"}

# Historical/debug output that is safe to rebuild.
CLEAN_DIRS = {"cycles", "diagnostics"}
LEGACY_FILES = {
    "eligible_jobs.json",
    "finalized_jobs.json",
    "application_manifest.json",
    "application_queue.json",
    "application_inspection.json",
    "application_autofill.json",
    "evening_report.md",
}


def cleanup(dry_run: bool = False) -> list[str]:
    GENERATED.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []

    for name in sorted(CLEAN_DIRS):
        path = GENERATED / name
        if path.exists():
            removed.append(str(path.relative_to(ROOT)))
            if not dry_run:
                shutil.rmtree(path)

    for name in sorted(LEGACY_FILES):
        path = GENERATED / name
        if path.exists():
            removed.append(str(path.relative_to(ROOT)))
            if not dry_run:
                path.unlink()

    # Remove accidental Python/cache/temp artifacts anywhere under generated,
    # but never traverse into or delete resume history.
    for path in list(GENERATED.rglob("*")):
        if any(part in PRESERVE_DIRS for part in path.relative_to(GENERATED).parts):
            continue
        if path.is_file() and (path.suffix in {".pyc", ".tmp", ".log"} or path.name == ".DS_Store"):
            removed.append(str(path.relative_to(ROOT)))
            if not dry_run:
                path.unlink()

    return removed


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Clean rebuildable job-agent output while preserving production state and resume history.")
    p.add_argument("--dry-run", action="store_true", help="Show what would be removed without deleting anything.")
    args = p.parse_args()
    removed = cleanup(args.dry_run)
    mode = "Would remove" if args.dry_run else "Removed"
    print(f"{mode} {len(removed)} item(s).")
    for item in removed:
        print(f" - {item}")
    print("Preserved production state:", ", ".join(sorted(PRESERVE_FILES)))
    print("Preserved resume history: generated/resumes/")
