from __future__ import annotations

import argparse
import os
import shutil
import stat
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
PRESERVE_DIRS = {"resumes", "llm_resume_cache"}

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
    "ai_application_results.json",
}


def _remove_readonly(func, path, exc_info):
    """Retry deletion after clearing Windows/OneDrive read-only attributes."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise exc_info[1]


def _rmtree(path: Path) -> None:
    # Clear read-only flags first; OneDrive/Windows can leave generated files
    # non-writable even though they are safe to remove.
    for item in path.rglob("*"):
        try:
            os.chmod(item, stat.S_IWRITE)
        except OSError:
            pass
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    try:
        shutil.rmtree(path, onexc=_remove_readonly)
    except TypeError:
        # Python <3.12 compatibility.
        shutil.rmtree(path, onerror=_remove_readonly)


def cleanup(dry_run: bool = False) -> list[str]:
    GENERATED.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []

    for name in sorted(CLEAN_DIRS):
        path = GENERATED / name
        if path.exists():
            removed.append(str(path.relative_to(ROOT)))
            if not dry_run:
                _rmtree(path)

    for name in sorted(LEGACY_FILES):
        path = GENERATED / name
        if path.exists():
            removed.append(str(path.relative_to(ROOT)))
            if not dry_run:
                path.unlink()

    # Remove accidental temp artifacts under generated, but preserve durable
    # resume history and the paid-LLM cache.
    for path in list(GENERATED.rglob("*")):
        if any(part in PRESERVE_DIRS for part in path.relative_to(GENERATED).parts):
            continue
        if path.is_file() and (path.suffix in {".pyc", ".tmp", ".log"} or path.name in {".DS_Store", "Thumbs.db"}):
            removed.append(str(path.relative_to(ROOT)))
            if not dry_run:
                path.unlink()

    # Python/pytest caches are always rebuildable and should never be committed
    # or treated as application state. Clean them across the project, excluding
    # the virtual environment and .git.
    for name in ("__pycache__", ".pytest_cache"):
        for path in list(ROOT.rglob(name)):
            rel=path.relative_to(ROOT)
            if any(part in {".venv", ".git"} for part in rel.parts):
                continue
            if path.is_dir():
                removed.append(str(rel))
                if not dry_run:_rmtree(path)

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
