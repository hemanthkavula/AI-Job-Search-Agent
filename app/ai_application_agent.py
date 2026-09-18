from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.config import load_profile

ROOT = Path(__file__).resolve().parents[1]


def _resolve_file(value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value)
    for candidate in ([p] if p.is_absolute() else [ROOT / p, p]):
        try:
            candidate = candidate.resolve()
            if candidate.exists() and candidate.is_file():
                return candidate
        except Exception:
            pass
    return None


def _profile_facts(profile: dict[str, Any]) -> dict[str, Any]:
    contact = profile.get("contact") or {}
    auth = profile.get("work_authorization") or {}
    return {
        "name": profile.get("name"),
        "email": contact.get("email"),
        "phone": contact.get("phone"),
        "linkedin": contact.get("linkedin"),
        "education": profile.get("education") or [],
        "experience": profile.get("experience") or [],
        "authorized_to_work_us": auth.get("authorized_to_work_us"),
        "requires_sponsorship_now": auth.get("requires_sponsorship_now"),
        "requires_sponsorship_future": auth.get("requires_sponsorship_future"),
        "work_authorization_statement": auth.get("statement"),
    }


def _task(item: dict[str, Any], profile: dict[str, Any], resume: Path) -> str:
    facts = _profile_facts(profile)
    known = item.get("known_answers") or {}
    payload = {
        "job_url": item.get("application_url") or item.get("url"),
        "company": item.get("company"),
        "title": item.get("title"),
        "discovery_source": item.get("source"),
        "resume_path": str(resume),
        "candidate": facts,
        "known_answers": known,
    }
    return f"""
You are operating a real job application for the candidate. Analyze the ACTUAL application UI before acting.
Application context:
{json.dumps(payload, indent=2, ensure_ascii=False)}

Goal:
1. Open the job URL and locate the employer's real application flow.
2. Inspect each page before filling it. Do not assume Workday, Greenhouse, Lever, Ashby, SmartRecruiters, iCIMS, Jobvite, or any other fixed ATS.
3. Prefer resume-assisted/autofill-with-resume when offered. Upload ONLY the exact resume_path above.
4. After resume parsing, inspect the resulting fields and correct deterministic candidate facts when needed.
5. Fill only answers supported by candidate facts or known_answers.
6. For "How did you hear about us?", inspect the ACTUAL options and choose a truthful option based on discovery_source/employer context. Never invent a referral, recruiter, staffing agency, school, or personal relationship.
7. Work authorization rules are authoritative:
   - authorized to work in the United States: YES
   - requires sponsorship now/currently: NO
   - requires sponsorship in the future: YES
   - combined now-or-future sponsorship question: YES
8. Navigate multi-step pages by inspecting the new page after every Next/Continue.
9. Do NOT guess salary, demographics/self-identification, disability/veteran answers, relocation/onsite willingness, legal attestations, employer-specific free text, or any fact absent from the supplied context.
10. If a required unknown question, CAPTCHA, MFA, verification, sign-in/account gate that cannot safely be completed, or other blocker appears: STOP and report MANUAL_ACTION_REQUIRED with the exact question/blocker.
11. NEVER click the final Submit/Submit Application button. Stop on the final Review page after checking that known answers and the intended resume are present.
12. Do not modify the resume file.

Return a concise final result containing one of:
READY_FOR_REVIEW
MANUAL_ACTION_REQUIRED
APPLICATION_FLOW_ERROR
and explain the current page, completed steps, and any unresolved required items.
"""


async def _run_one(item: dict[str, Any], profile: dict[str, Any], headed: bool) -> dict[str, Any]:
    try:
        from browser_use import Agent, Browser, ChatOpenAI
    except ImportError as exc:
        return {"external_id": item.get("external_id"), "status": "SETUP_REQUIRED",
                "error": f"browser-use is not installed: {exc}"}

    resume = _resolve_file(item.get("resume_pdf") or item.get("resume_path") or item.get("pdf"))
    if not resume:
        return {"external_id": item.get("external_id"), "status": "HOLD_ARTIFACT_VALIDATION",
                "error": "validated resume PDF was not found"}

    url = item.get("application_url") or item.get("url")
    if not url:
        return {"external_id": item.get("external_id"), "status": "APPLICATION_FLOW_ERROR",
                "error": "application URL missing"}

    model = os.getenv("APPLICATION_AGENT_MODEL", "gpt-5.6-luna")
    llm = ChatOpenAI(model=model)
    browser = Browser(headless=not headed)
    # Browser Use blocks arbitrary local uploads unless paths are explicitly
    # allow-listed. The resume has already passed our artifact validation, so
    # expose only this job's exact PDF to the agent.
    agent = Agent(
        task=_task(item, profile, resume),
        llm=llm,
        browser=browser,
        available_file_paths=[str(resume)],
    )
    try:
        history = await agent.run(max_steps=int(os.getenv("APPLICATION_AGENT_MAX_STEPS", "80")))
        final = history.final_result() or ""
        upper = final.upper()
        if "READY_FOR_REVIEW" in upper:
            status = "READY_FOR_REVIEW"
        elif "MANUAL_ACTION_REQUIRED" in upper:
            status = "MANUAL_ACTION_REQUIRED"
        else:
            status = "APPLICATION_FLOW_ERROR"
        return {"external_id": item.get("external_id"), "url": url, "status": status,
                "agent_result": final, "submitted": False, "resume_pdf": str(resume)}
    except Exception as exc:
        return {"external_id": item.get("external_id"), "url": url,
                "status": "APPLICATION_FLOW_ERROR", "error": str(exc), "submitted": False}
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


async def _main_async(args) -> int:
    load_dotenv()
    queue_path = Path(args.queue)
    items = json.loads(queue_path.read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("applications") or items.get("items") or []
    profile = load_profile()
    results = []
    for item in items[: args.limit if args.limit else None]:
        results.append(await _run_one(item, profile, args.headed))
    out = ROOT / "generated" / "ai_application_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"Results: {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="AI browser agent for ATS-independent job application completion")
    ap.add_argument("--queue", required=True)
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
