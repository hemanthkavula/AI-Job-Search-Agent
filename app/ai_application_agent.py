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
        "address": contact.get("address") or {},
        "education": profile.get("education") or [],
        "experience": profile.get("experience") or [],
        "authorized_to_work_us": auth.get("authorized_to_work_us"),
        "requires_sponsorship_now": auth.get("requires_sponsorship_now"),
        "requires_sponsorship_future": auth.get("requires_sponsorship_future"),
        "work_authorization_statement": auth.get("statement"),
    }


def _source_context(item: dict[str, Any]) -> dict[str, Any]:
    """Separate ATS hosting technology from the truthful recruiting source."""
    raw = str(item.get("source") or "").strip()
    norm = raw.lower()
    ats_hosts = {
        "workday", "greenhouse", "lever", "ashby", "smartrecruiters",
        "icims", "jobvite"
    }
    if norm in ats_hosts:
        return {
            "raw_source": raw,
            "source_kind": "ATS_HOST",
            "ats_provider": raw,
            "recruiting_source": "direct employer careers/application site",
            "instruction": (
                f"{raw} is the ATS hosting provider, NOT a job board and NOT the answer "
                "to 'How did you hear about us?'. Prefer an actual employer/company "
                "website or careers-site option when present. Do not select Job Board "
                f"merely because the application is hosted by {raw}."
            ),
        }
    return {
        "raw_source": raw,
        "source_kind": "DISCOVERY_SOURCE",
        "ats_provider": None,
        "recruiting_source": raw,
        "instruction": (
            "This is the recorded discovery source. Use it only when the application's "
            "actual choices truthfully match it; otherwise choose the closest truthful "
            "web/company-careers option."
        ),
    }


def _task(item: dict[str, Any], profile: dict[str, Any], resume: Path) -> str:
    facts = _profile_facts(profile)
    known = item.get("known_answers") or {}
    payload = {
        "job_url": item.get("application_url") or item.get("url"),
        "company": item.get("company"),
        "title": item.get("title"),
        "source_context": _source_context(item),
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
3. Prefer resume-assisted/autofill-with-resume when offered. Upload ONLY the exact resume_path above. RENDERING RECOVERY: after selecting an application path, a temporarily blank/header-footer-only page is an ordinary recoverable loading state, NOT MANUAL_ACTION_REQUIRED. Wait and re-inspect at least twice (use increasing waits such as 5 then 8 seconds). If still blank, reload once and wait/re-inspect. If the preferred resume-autofill route still does not render, go back to the application-start choice and use Apply Manually (or the equivalent alternate application path) when available. Continue the application there and upload the exact resume later if that flow offers a resume/document control. Do not abandon an application solely because one route temporarily fails to render.
4. After resume parsing, inspect the resulting fields and correct deterministic candidate facts when needed.
5. Fill only answers supported by candidate facts or known_answers. Treat ALL supplied candidate fields as available facts, including phone. Never say phone is unsupported when candidate.phone is present.
6. For "How did you hear about us?", use source_context carefully. An ATS host (Workday, Greenhouse, Lever, Ashby, SmartRecruiters, iCIMS, Jobvite) is application infrastructure, NOT a job board/recruiting source. Never type/select "Workday" or choose "Job Board" merely because source_kind=ATS_HOST. When source_kind=ATS_HOST, inspect the ACTUAL choices and prefer a truthful employer/company website or careers-site choice (for example an employer-named .com/careers option) when available, then generic Website/Web/Online if needed. Only choose Job Board when the recorded source is actually a job board or the provenance otherwise supports it. Search/select controls may be hierarchical: selecting a parent category is NOT complete if child options appear. Continue until a leaf option is visibly committed and the picker is closed. Never invent a referral, recruiter, staffing agency, school, or personal relationship.
7. Work authorization rules are authoritative:
   - authorized to work in the United States: YES
   - requires sponsorship now/currently: NO
   - requires sponsorship in the future: YES
   - combined now-or-future sponsorship question: YES
8. Navigate multi-step pages by inspecting the new page after every Next/Continue. Do not stop merely because a dropdown remains open, a selection needs confirmation, a known field needs correction, or a Next button needs another attempt. Resolve ordinary UI state yourself and continue. MANUAL_ACTION_REQUIRED is only for a genuinely unknown required answer, CAPTCHA/MFA/verification, unavoidable authentication gate, or an unrecoverable browser/site failure.
9. Do NOT guess salary, demographics/self-identification, disability/veteran answers, relocation/onsite willingness, legal attestations, employer-specific free text, or any fact absent from the supplied context.
10. If a required unknown question, CAPTCHA, MFA, verification, sign-in/account gate that cannot safely be completed, or unrecoverable blocker appears: STOP and report MANUAL_ACTION_REQUIRED with the exact question/blocker. Before stopping, make reasonable UI-only recovery attempts (wait/re-inspect blank or partially rendered pages, reload once, try an available alternate application route, close picker with Escape/click outside, verify committed selection, retry Next after validation/rendering, scroll to errors). Never classify a temporary blank/loading page, a normal open dropdown, or a supplied fact such as phone as manual action.
11. NEVER click the final Submit/Submit Application button. Stop on the final Review page after checking that known answers and the intended resume are present.
12. Do not modify the resume file.
13. Before declaring a page complete, verify visible required fields and committed selections. Do not claim a radio/dropdown was selected unless the UI visibly reflects it.
14. Continue until Review unless rule 10 truly applies. The fact that one interaction is uncertain is a reason to inspect/retry, not a reason to stop. CRITICAL: do not call done, APPLICATION_FLOW_ERROR, or MANUAL_ACTION_REQUIRED while there is an obvious actionable control that advances the application (for example Select file/upload, Next, Continue, Save and Continue, a required field with a known answer, or an available alternate route). Execute the next supported action instead. APPLICATION_FLOW_ERROR is reserved for a genuinely unrecoverable browser/site failure after the recovery rules are exhausted.
15. STUBBORN CONTROL RECOVERY: if a normal click on a radio button, checkbox, dropdown option, or button does not visibly commit the intended state, do NOT repeat the same indexed click more than twice and do NOT stop. Call the activate_form_control tool with the exact visible question/label and the already-supported intended value. The recovery tool uses semantic targeting and portable click/keyboard activation for radio/checkbox controls. Then inspect the page and verify the state. If semantic recovery itself reports a tool-side exception, treat that as an automation failure to recover from: try the visible answer label/container, focus the control and press Space/Enter, or re-inspect for a native input. Do not call MANUAL_ACTION_REQUIRED solely because the recovery tool failed. This recovery is generic across ATS sites and must never be used to invent an answer.
16. PHONE RECOVERY: when the form has a separate country/region calling-code control (for example United States +1), the phone-number field should normally contain only the national 10-digit number. If a truthful supplied phone fails validation, treat formatting as an ordinary recoverable UI issue, not MANUAL_ACTION_REQUIRED. Inspect the actual phone input and country-code state, then try reasonable representations of the same digits only (digits-only, standard U.S. formatting, hyphenated/dotted/spaced forms, and +1 form only when there is no separate +1 control). After each attempt, blur/focus away or otherwise trigger validation and inspect the error. Never alter the underlying phone digits. Exhaust these UI-only format attempts before considering the site unrecoverable.
17. ROUTE FALLBACK: remember application choices observed earlier in the session. If a preferred route fails after the rendering-recovery sequence, navigate back and use another truthful available route such as Apply Manually instead of stopping. Re-analyze that route from scratch; never assume its fields match the failed route.
18. ACTIONABLE-PAGE INVARIANT: before producing any terminal result, inspect the current page one final time. If the page contains an actionable application control whose action is supported by supplied facts/files, you MUST use it and continue. In particular, when the exact resume_path is available and a file upload/select-file control is visible, upload that file immediately; do not terminate merely after observing the control. After upload, wait for parsing/validation as needed and use Next/Continue when enabled.

Return a concise final result containing one of:
READY_FOR_REVIEW
MANUAL_ACTION_REQUIRED
APPLICATION_FLOW_ERROR
and explain the current page, completed steps, and any unresolved required items.
"""


def _build_tools():
    """Add generic semantic recovery for controls the normal browser index cannot activate."""
    from browser_use import ActionResult, Tools

    tools = Tools()

    @tools.action(
        description=(
            "Finish the application-agent task. This action enforces terminal-state policy: "
            "READY_FOR_REVIEW is accepted only after reaching Review; MANUAL_ACTION_REQUIRED "
            "is accepted only for a genuine unknown required answer, CAPTCHA/MFA/verification/"
            "authentication blocker; APPLICATION_FLOW_ERROR is accepted only for a genuine "
            "unrecoverable browser/site failure. If supported actionable fields remain, the "
            "finish request is rejected and the agent must continue."
        )
    )
    async def done(
        text: str,
        success: bool = False,
        files_to_display: list[str] | None = None,
    ) -> ActionResult:
        normalized = (text or "").lower()
        first_line = (text or "").strip().splitlines()[0].upper() if (text or "").strip() else ""

        if "READY_FOR_REVIEW" in first_line:
            if "review" not in normalized:
                return ActionResult(
                    extracted_content=(
                        "TERMINAL_REJECTED: READY_FOR_REVIEW requires the actual Review page. "
                        "Inspect the current page and continue through supported actionable controls."
                    ),
                    is_done=False,
                    success=False,
                )
        elif "MANUAL_ACTION_REQUIRED" in first_line:
            genuine_manual_markers = (
                "captcha", "mfa", "multi-factor", "verification code", "authentication",
                "sign-in", "sign in", "login required", "unknown required",
                "not supplied", "not provided", "cannot safely answer",
            )
            ordinary_incomplete_markers = (
                "still needs to be entered", "remains select one", "picker is open",
                "not yet selected", "not yet committed", "phone number still needs",
                "state remains", "supported fields unresolved",
            )
            has_genuine_blocker = any(marker in normalized for marker in genuine_manual_markers)
            ordinary_only = any(marker in normalized for marker in ordinary_incomplete_markers)
            if ordinary_only or not has_genuine_blocker:
                return ActionResult(
                    extracted_content=(
                        "TERMINAL_REJECTED: the current state is an ordinary incomplete form, not a "
                        "manual-action blocker. Re-inspect the page and complete every visible field/control "
                        "supported by candidate facts (including address/state/phone/source/radios), then "
                        "use Next/Continue. Only stop for a genuinely unknown required answer, CAPTCHA, "
                        "MFA/verification/authentication gate, or unrecoverable failure."
                    ),
                    is_done=False,
                    success=False,
                )
        elif "APPLICATION_FLOW_ERROR" in first_line:
            failure_markers = (
                "unrecoverable", "browser crashed", "browser failure", "site failure",
                "navigation failed", "page unavailable",
            )
            if not any(marker in normalized for marker in failure_markers):
                return ActionResult(
                    extracted_content=(
                        "TERMINAL_REJECTED: APPLICATION_FLOW_ERROR requires a concrete unrecoverable "
                        "browser/site failure after recovery attempts. Continue the application."
                    ),
                    is_done=False,
                    success=False,
                )
        else:
            return ActionResult(
                extracted_content=(
                    "TERMINAL_REJECTED: final text must begin with READY_FOR_REVIEW, "
                    "MANUAL_ACTION_REQUIRED, or APPLICATION_FLOW_ERROR. Continue if actionable controls remain."
                ),
                is_done=False,
                success=False,
            )

        return ActionResult(
            is_done=True,
            success=success,
            extracted_content=text,
            long_term_memory=f"Task completed with terminal state: {first_line}",
        )

    @tools.action(
        description=(
            "Recover a stubborn visible form control by semantic description. Use this after normal indexed "
            "clicks fail. Describe the exact visible question and intended supported value. The action tries "
            "the semantic target itself, its label/container, and keyboard activation. It is generic across ATS "
            "sites and must never invent an answer or target a final Submit control."
        )
    )
    async def activate_form_control(
        question: str,
        value: str,
        browser_session,
        page_extraction_llm,
    ) -> ActionResult:
        page = await browser_session.must_get_current_page()
        prompts = [
            f'The actual input/radio/checkbox control labeled "{value}" for question "{question}"',
            f'The visible text or label "{value}" associated with question "{question}"',
            f'The clickable row/container for answer "{value}" nearest question "{question}"',
        ]
        errors = []
        for prompt in prompts:
            try:
                element = await page.get_element_by_prompt(prompt, page_extraction_llm)
                if element is None:
                    errors.append(f"not found: {prompt}")
                    continue

                # Keep this recovery deliberately API-light. Some Browser Use DOM element
                # wrappers do not implement get_basic_info()/check() consistently across
                # versions. click() plus keyboard activation is more portable.
                try:
                    await element.click()
                    return ActionResult(
                        extracted_content=(
                            f'Activated semantic target for "{question}" -> "{value}" by click. '
                            "Inspect and verify the selected/checked state now."
                        )
                    )
                except Exception as click_exc:
                    errors.append(f"click failed for {prompt}: {click_exc}")
                    try:
                        await element.focus()
                        await page.send_keys(" ")
                        return ActionResult(
                            extracted_content=(
                                f'Activated semantic target for "{question}" -> "{value}" with keyboard Space. '
                                "Inspect and verify the selected/checked state now."
                            )
                        )
                    except Exception as key_exc:
                        errors.append(f"keyboard failed for {prompt}: {key_exc}")
            except Exception as semantic_exc:
                errors.append(f"semantic lookup failed for {prompt}: {semantic_exc}")
                continue
        return ActionResult(
            extracted_content=(
                f'Could not activate semantic control for "{question}" -> "{value}". '
                f'Attempts: {"; ".join(errors)}. Continue with another visible/keyboard interaction if available; '
                "do not classify this tool failure alone as a manual blocker."
            )
        )

    return tools

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
    tools = _build_tools()
    agent = Agent(
        task=_task(item, profile, resume),
        llm=llm,
        browser=browser,
        tools=tools,
        available_file_paths=[str(resume)],
    )
    try:
        history = await agent.run(max_steps=int(os.getenv("APPLICATION_AGENT_MAX_STEPS", "160")))
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
