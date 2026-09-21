from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from app.config import load_profile

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "browser_worker" / "stagehand_worker.mjs"


def _public_profile(profile: dict) -> dict:
    keys = ("name", "contact", "work_authorization", "application_preferences",
            "experience", "skills", "education")
    return {k: profile.get(k) for k in keys if profile.get(k) is not None}


def _run_one(item: dict, profile: dict, allow_submit: bool, headless: bool) -> dict:
    resume = Path(item.get("resume_path") or "")
    if not resume.is_absolute():
        resume = ROOT / resume
    if not resume.exists():
        return {
            "external_id": item.get("external_id"), "url": item.get("url"),
            "status": "MANUAL_ACTION_REQUIRED", "submitted": False,
            "submission_attempted": False,
            "reason": f"Approved resume not found: {resume}", "blockers": ["resume_missing"],
        }

    payload = {
        "url": item.get("url"),
        "resume_path": str(resume.resolve()),
        "profile": _public_profile(profile),
        "known_answers": item.get("known_answers") or {},
        "description": item.get("description") or "",
        "allow_submit": bool(allow_submit),
    }
    env = os.environ.copy()
    env["STAGEHAND_HEADLESS"] = "true" if headless else "false"
    proc = subprocess.run(
        ["node", str(WORKER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        timeout=float(os.getenv("STAGEHAND_APPLICATION_TIMEOUT", "1800")),
    )
    lines = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
    data = {}
    for line in reversed(lines):
        try:
            candidate = json.loads(line)
            if isinstance(candidate, dict) and "submitted" in candidate:
                data = candidate
                break
        except json.JSONDecodeError:
            continue
    if not data:
        reason = proc.stderr.strip()[-4000:] or proc.stdout.strip()[-4000:] or f"Stagehand worker exited {proc.returncode}"
        return {
            "external_id": item.get("external_id"), "url": item.get("url"),
            "status": "MANUAL_ACTION_REQUIRED", "submitted": False,
            "submission_attempted": False, "reason": reason, "blockers": [],
        }

    submitted = bool(data.get("submitted"))
    attempted = bool(data.get("submission_attempted"))
    blocker = data.get("blocker") or ""
    if submitted:
        status = "SUBMITTED"
    elif data.get("ready_for_review"):
        status = "AUTOFILLED_REVIEW_REQUIRED"
    else:
        status = "MANUAL_ACTION_REQUIRED"
    return {
        "external_id": item.get("external_id"),
        "url": data.get("final_url") or item.get("url"),
        "status": status,
        "submitted": submitted,
        "submission_attempted": attempted,
        "reason": data.get("reason") or "Stagehand stopped without positive confirmation.",
        "blockers": [blocker] if blocker else [],
        "resume_uploaded": bool(data.get("resume_uploaded")),
        "final_url": data.get("final_url"),
    }


def run(queue_path="generated/application_queue.json",
        output="generated/stagehand_application_results.json", limit=None,
        headless=False, review_seconds=0, inspect_only=False,
        wait_for_human_seconds=0, allow_submit=False, before_submit=None, **_):
    if inspect_only:
        allow_submit = False
    rows = json.loads((ROOT / queue_path).read_text(encoding="utf-8"))
    rows = [x for x in rows if x.get("status") == "READY_FOR_ATS_ADAPTER"]
    if limit is not None:
        rows = rows[:limit]
    profile = load_profile()
    results = []
    for item in rows:
        try:
            results.append(_run_one(item, profile, allow_submit, headless))
        except subprocess.TimeoutExpired:
            results.append({
                "external_id": item.get("external_id"), "url": item.get("url"),
                "status": "MANUAL_ACTION_REQUIRED", "submitted": False,
                "submission_attempted": False,
                "reason": "Stagehand application worker timed out.", "blockers": [],
            })
        except Exception as exc:
            results.append({
                "external_id": item.get("external_id"), "url": item.get("url"),
                "status": "MANUAL_ACTION_REQUIRED", "submitted": False,
                "submission_attempted": False,
                "reason": f"Stagehand execution failed: {type(exc).__name__}: {exc}",
                "blockers": [],
            })
    out = ROOT / output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--queue", default="generated/application_queue.json")
    p.add_argument("--output", default="generated/stagehand_application_results.json")
    p.add_argument("--limit", type=int)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--allow-submit", action="store_true")
    a = p.parse_args()
    print(json.dumps(run(a.queue, a.output, a.limit, headless=a.headless,
                         allow_submit=a.allow_submit), indent=2))
