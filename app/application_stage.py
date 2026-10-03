from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.application_queue import _application_gate
from app.config import load_profile
from app.job_ledger import _lookup, load_ledger, record_seen, save_ledger

ROOT = Path(__file__).resolve().parents[1]
CYCLES_DIR = ROOT / "generated" / "cycles"
DEFAULT_LEDGER = ROOT / "generated" / "job_ledger.json"
RESULTS_PATH = ROOT / "generated" / "application_stage_results.json"
ET = ZoneInfo("America/New_York")

CONFIRMATION_MARKERS = (
    "application submitted",
    "application has been submitted",
    "successfully submitted",
    "thank you for applying",
    "thank you for your application",
    "application received",
    "confirmation number",
    "confirmation id",
)


def _latest_summary() -> Path | None:
    rows = sorted(CYCLES_DIR.glob("*_summary.json"))
    return rows[-1] if rows else None


def _queue_from_summary(summary_path: Path | None) -> Path | None:
    if not summary_path or not summary_path.exists():
        return None
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    value = summary.get("application_queue")
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def resolve_queue(explicit: str | None = None) -> tuple[Path | None, Path | None]:
    summary = _latest_summary()
    if explicit:
        path = Path(explicit)
        return (path if path.is_absolute() else ROOT / path), summary
    return _queue_from_summary(summary), summary


def _profile_facts(profile: dict[str, Any]) -> dict[str, Any]:
    contact = profile.get("contact") or {}
    auth = profile.get("work_authorization") or {}
    return {
        "name": profile.get("name"),
        "email": contact.get("email"),
        "phone": contact.get("phone"),
        "linkedin": contact.get("linkedin"),
        "address": contact.get("address") or {},
        "education": profile.get("education") or [],
        "experience": profile.get("experience") or [],
        "authorized_to_work_us": auth.get("authorized_to_work_us"),
        "requires_sponsorship_now": auth.get("requires_sponsorship_now"),
        "requires_sponsorship_future": auth.get("requires_sponsorship_future"),
        "work_authorization_statement": auth.get("statement"),
        "application_preferences": profile.get("application_preferences") or {},
    }


def _source_context(item: dict[str, Any]) -> dict[str, Any]:
    source = str(item.get("source") or "").strip()
    ats_hosts = {
        "workday", "greenhouse", "lever", "ashby", "smartrecruiters", "icims",
        "jobvite", "oracle", "ukg", "bamboohr", "breezyhr", "recruitee",
    }
    if source.lower() in ats_hosts:
        return {
            "kind": "ATS_HOST",
            "raw": source,
            "truthful_recruiting_source": "direct employer careers/application site",
        }
    return {"kind": "DISCOVERY_SOURCE", "raw": source}


def build_task(item: dict[str, Any], profile: dict[str, Any], resume: Path, allow_submit: bool) -> str:
    payload = {
        "job_url": item.get("url"),
        "company": item.get("company"),
        "title": item.get("title"),
        "source_context": _source_context(item),
        "resume_path": str(resume),
        "candidate": _profile_facts(profile),
        "known_answers": item.get("known_answers") or {},
        "application_run_date": datetime.now(ET).strftime("%m/%d/%Y"),
        "allow_final_submit": allow_submit,
    }
    return f"""
Complete exactly one real job application. Inspect the ACTUAL UI before acting.

APPLICATION CONTEXT
{json.dumps(payload, indent=2, ensure_ascii=False)}

RULES
1. Use only supplied candidate facts, known_answers, approved application_preferences, and the exact resume_path. Never invent facts.
2. Upload only the exact validated PDF at resume_path. Never modify it.
3. Fill supported required fields. Optional fields should normally remain blank unless necessary for the form to work.
4. Work authorization is authoritative: authorized to work in U.S.=YES; sponsorship now/currently=NO; sponsorship in future=YES; combined now-or-future sponsorship=YES. Explicit no-sponsorship/no-future-sponsorship/no-immigration-support language is NOT an eligibility blocker; continue if other requirements pass.
5. If the application itself newly reveals a U.S.-citizenship-only requirement or required security/public-trust/Secret/Top Secret clearance, return INELIGIBLE_AT_APPLICATION and do not submit.
6. Never guess salary/compensation, employer-specific free text, referral relationships, or an unsupported required fact. Return MANUAL_ACTION_REQUIRED with the exact unresolved question.
7. Do NOT bypass CAPTCHA, MFA, one-time verification, or unavoidable sign-in/authentication. Return MANUAL_ACTION_REQUIRED with the blocker.
8. For "How did you hear about us?", an ATS host is infrastructure, not a recruiting source. Use company website/careers for direct ATS provenance; use a job board only when source_context truthfully identifies that board.
9. Approved application_preferences may be used only for semantically equivalent required questions. Accept required application terms/privacy acknowledgments only within the approved scope; do not accept optional marketing. Use the approved signature only for the application/e-signature context.
10. Recover ordinary loading/dropdown/phone-format/Next/Continue issues yourself. These are not manual blockers.
11. Before final submission verify correct company/title/application, exact resume, all required fields committed, identity/contact facts consistent, work-authorization answers match rule 4, no visible validation errors, and no unresolved required questions.
12. If allow_final_submit=false, never click final Submit; return READY_FOR_REVIEW on the final review page.
13. If allow_final_submit=true and every pre-submit check passes, click final Submit/Submit Application exactly ONCE. Wait for visible employer/ATS confirmation. Only then return SUBMITTED. If outcome is ambiguous, do not click Submit again; return SUBMISSION_ATTEMPTED.
14. Before any terminal result, re-inspect the page and continue through any supported required field or safe Next/Continue action.

FIRST LINE must be exactly one of:
SUBMITTED
SUBMISSION_ATTEMPTED
READY_FOR_REVIEW
MANUAL_ACTION_REQUIRED
INELIGIBLE_AT_APPLICATION
APPLICATION_FLOW_ERROR

Then explain the final page/state. For SUBMITTED include the visible confirmation text/reference identifier.
"""


def classify_result(text: str) -> str:
    raw = (text or "").strip()
    first = raw.splitlines()[0].strip().upper() if raw else ""
    normalized = raw.lower()
    if first == "SUBMITTED":
        return "SUBMITTED" if any(m in normalized for m in CONFIRMATION_MARKERS) else "SUBMISSION_ATTEMPTED"
    if first in {
        "SUBMISSION_ATTEMPTED", "READY_FOR_REVIEW", "MANUAL_ACTION_REQUIRED",
        "INELIGIBLE_AT_APPLICATION", "APPLICATION_FLOW_ERROR",
    }:
        return first
    return "APPLICATION_FLOW_ERROR"


def _resolve_resume(item: dict[str, Any]) -> Path | None:
    value = item.get("resume_path")
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = ROOT / path
    try:
        path = path.resolve()
    except Exception:
        return None
    return path if path.is_file() and path.suffix.lower() == ".pdf" else None


def _already_submitted(item: dict[str, Any], ledger: dict) -> bool:
    _, row = _lookup(item, ledger)
    return bool(row and row.get("application_status") in {"SUBMITTED", "SUBMITTED_CONFIRMED"})


async def _run_browser_agent(item: dict[str, Any], profile: dict[str, Any], resume: Path, allow_submit: bool) -> dict[str, Any]:
    try:
        from browser_use import Agent, Browser, ChatOpenAI
    except Exception as exc:
        return {
            "external_id": item.get("external_id"),
            "status": "SETUP_REQUIRED",
            "submitted": False,
            "error": f"browser-use unavailable: {exc}",
        }

    model = os.getenv("APPLICATION_AGENT_MODEL", "gpt-5.6-luna")
    max_steps = int(os.getenv("APPLICATION_AGENT_MAX_STEPS", "80"))
    timeout_seconds = int(os.getenv("APPLICATION_AGENT_TIMEOUT_SECONDS", "600"))
    browser = None
    started = False
    try:
        browser = Browser(headless=True)
        llm = ChatOpenAI(model=model)
        agent = Agent(
            task=build_task(item, profile, resume, allow_submit),
            llm=llm,
            browser=browser,
            available_file_paths=[str(resume)],
        )
        started = True
        history = await asyncio.wait_for(agent.run(max_steps=max_steps), timeout=timeout_seconds)
        final = history.final_result() if hasattr(history, "final_result") else str(history)
        status = classify_result(final or "")
        return {
            "external_id": item.get("external_id"),
            "company": item.get("company"),
            "title": item.get("title"),
            "url": item.get("url"),
            "status": status,
            "submitted": status == "SUBMITTED",
            "agent_result": final or "",
            "resume_path": str(resume),
        }
    except asyncio.TimeoutError:
        return {
            "external_id": item.get("external_id"),
            "status": "APPLICATION_FLOW_ERROR",
            "submitted": False,
            "error": f"application agent exceeded {timeout_seconds}s timeout",
        }
    except Exception as exc:
        return {
            "external_id": item.get("external_id"),
            "status": "APPLICATION_FLOW_ERROR" if started else "SETUP_REQUIRED",
            "submitted": False,
            "error": str(exc),
        }
    finally:
        if browser is not None:
            try:
                await browser.stop()
            except Exception:
                pass


def _record_result(item: dict[str, Any], result: dict[str, Any], ledger: dict) -> None:
    status = result.get("status")
    details = result.get("agent_result") or result.get("error")
    extra = {"application_result": details, "application_result_path": str(RESULTS_PATH)}
    ledger_status = status
    if status == "SUBMITTED":
        ledger_status = "SUBMITTED_CONFIRMED"
        extra["submitted_at"] = datetime.now(ET).isoformat()
    elif status == "SUBMISSION_ATTEMPTED":
        extra["submission_attempted"] = True
        extra["submission_attempt"] = datetime.now(ET).isoformat()
    elif status == "INELIGIBLE_AT_APPLICATION":
        ledger_status = "PERMANENT_SKIP"
        extra["application_reason"] = details or "Citizenship/clearance restriction discovered during application."
    elif status in {"MANUAL_ACTION_REQUIRED", "APPLICATION_FLOW_ERROR"}:
        ledger_status = "MANUAL_ACTION_REQUIRED"
        extra["application_reason"] = details
    elif status == "SETUP_REQUIRED":
        # Keep the prior READY_TO_APPLY state so a later healthy runtime can retry.
        return
    elif status == "READY_FOR_REVIEW":
        ledger_status = "READY_TO_APPLY"
    record_seen(item, ledger, ledger_status, **extra)


def _patch_summary(summary_path: Path | None, results: list[dict[str, Any]], enabled: bool) -> None:
    if not summary_path or not summary_path.exists():
        return
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return
    summary["application_stage_enabled"] = enabled
    summary["applications_processed"] = len(results)
    summary["applications_submitted"] = sum(r.get("status") == "SUBMITTED" for r in results)
    summary["applications_submission_attempted"] = sum(r.get("status") == "SUBMISSION_ATTEMPTED" for r in results)
    summary["applications_manual_action"] = sum(r.get("status") == "MANUAL_ACTION_REQUIRED" for r in results)
    summary["applications_ineligible_at_application"] = sum(r.get("status") == "INELIGIBLE_AT_APPLICATION" for r in results)
    summary["application_setup_required"] = sum(r.get("status") == "SETUP_REQUIRED" for r in results)
    summary["application_results"] = str(RESULTS_PATH.relative_to(ROOT))
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


async def run(
    queue: str | None = None,
    ledger_path: str | Path = DEFAULT_LEDGER,
    allow_submit: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    queue_path, summary_path = resolve_queue(queue)
    if not queue_path or not queue_path.exists():
        results: list[dict[str, Any]] = []
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_PATH.write_text("[]\n", encoding="utf-8")
        _patch_summary(summary_path, results, enabled=True)
        return {
            "enabled": True,
            "queue": str(queue_path) if queue_path else None,
            "processed": 0,
            "submitted": 0,
            "results": str(RESULTS_PATH),
        }

    rows = json.loads(queue_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("application queue must be a JSON list")
    profile = load_profile()
    ledger = load_ledger(ledger_path)
    results: list[dict[str, Any]] = []
    selected = rows if limit is None else rows[: max(0, limit)]

    for item in selected:
        if item.get("status") != "READY_FOR_ATS_ADAPTER":
            continue
        if _already_submitted(item, ledger):
            results.append({"external_id": item.get("external_id"), "status": "SKIP_ALREADY_SUBMITTED", "submitted": False})
            continue

        gate_ok, gate_reasons = _application_gate(item, profile)
        if not gate_ok:
            result = {
                "external_id": item.get("external_id"),
                "status": "INELIGIBLE_AT_APPLICATION",
                "submitted": False,
                "agent_result": "Pre-submit eligibility recheck failed: " + "; ".join(gate_reasons),
            }
        else:
            resume = _resolve_resume(item)
            if not resume:
                result = {
                    "external_id": item.get("external_id"),
                    "status": "MANUAL_ACTION_REQUIRED",
                    "submitted": False,
                    "error": "Validated resume PDF is missing at application time.",
                }
            else:
                result = await _run_browser_agent(item, profile, resume, allow_submit)

        results.append(result)
        _record_result(item, result, ledger)
        save_ledger(ledger, ledger_path)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    _patch_summary(summary_path, results, enabled=True)
    return {
        "enabled": True,
        "submit_enabled": allow_submit,
        "queue": str(queue_path),
        "processed": len(results),
        "submitted": sum(r.get("status") == "SUBMITTED" for r in results),
        "submission_attempted": sum(r.get("status") == "SUBMISSION_ATTEMPTED" for r in results),
        "manual_action": sum(r.get("status") == "MANUAL_ACTION_REQUIRED" for r in results),
        "setup_required": sum(r.get("status") == "SETUP_REQUIRED" for r in results),
        "results": str(RESULTS_PATH),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded ATS-independent post-queue application executor.")
    parser.add_argument("--queue", help="Application queue JSON. Defaults to latest production-cycle queue.")
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--submit", action="store_true", help="Allow exactly-once final submission after pre-submit validation.")
    args = parser.parse_args()
    result = asyncio.run(run(args.queue, args.ledger, allow_submit=args.submit, limit=args.limit))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
