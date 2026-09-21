from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from app.config import load_profile

ROOT = Path(__file__).resolve().parents[1]

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "submitted": {"type": "boolean"},
        "confirmation_text": {"type": "string"},
        "final_url": {"type": "string"},
        "blocker": {"type": "string"},
    },
    "required": ["submitted"],
}

def _public_profile(profile: dict) -> dict:
    """Application facts only. Secrets/passwords are intentionally excluded."""
    keys = ("name", "contact", "work_authorization", "application_preferences",
            "experience", "skills", "education")
    return {k: profile.get(k) for k in keys if profile.get(k) is not None}

def _prompt(item: dict, profile: dict, resume_uri: str | None, allow_submit: bool) -> str:
    facts=json.dumps(_public_profile(profile), ensure_ascii=False)
    known=json.dumps(item.get("known_answers") or {}, ensure_ascii=False)
    jd=(item.get("description") or "")[:12000]
    submit=("You are authorized to submit the application after reviewing it."
            if allow_submit else
            "Do not perform the final submission. Stop on the final review page.")
    resume=("The approved resume is available at this uploaded file URL: "+resume_uri
            if resume_uri else
            "No resume file was made available; stop if a resume is required.")
    return f"""Complete this job application autonomously from the supplied starting URL.
Use the live rendered website and its current state; do not assume an ATS-specific flow.
{submit}
{resume}

Candidate facts (authoritative; never invent or contradict them):
{facts}

Known application answers:
{known}

Job description/context:
{jd}

Requirements:
- Use the existing approved resume; never generate or rewrite a resume.
- Navigate login/account creation, forms, uploads, application questions, disclosures, review and submission as needed.
- Only answer from the candidate facts, known answers, resume and job context. Never fabricate credentials, certifications, employment facts, dates, compensation, demographics, or technical experience.
- Do not bypass CAPTCHA, MFA, identity verification, or other security challenges. If one prevents progress, stop and report it as blocker.
- Do not fill honeypot/robot-only fields.
- Treat success as submitted=true only when the rendered site positively confirms the application was submitted/received. A click on Submit alone is not confirmation.
- If submission is not positively confirmed, return submitted=false and explain the blocker or uncertainty.
"""

async def _run_one(client, item: dict, profile: dict, allow_submit: bool) -> dict:
    resume=Path(item.get("resume_path") or "")
    if not resume.is_absolute(): resume=ROOT/resume
    resume_uri=None
    if resume.exists():
        with resume.open("rb") as resume_file:
            uploaded=await client.upload_file(file=resume_file)
        resume_uri=getattr(uploaded, "presigned_url", None) or getattr(uploaded, "s3uri", None)
    result=await client.run_task(
        url=item.get("url"),
        prompt=_prompt(item, profile, resume_uri, allow_submit),
        wait_for_completion=True,
        timeout=float(os.getenv("SKYVERN_APPLICATION_TIMEOUT", "1800")),
        max_steps=int(os.getenv("SKYVERN_APPLICATION_MAX_STEPS", "80")),
        data_extraction_schema=RESULT_SCHEMA,
        title=f"Job application: {item.get('company','')} - {item.get('title','')}",
    )
    output=getattr(result, "output", None)
    if isinstance(output, str):
        try: output=json.loads(output)
        except Exception: output={"submitted":False,"blocker":output}
    if not isinstance(output, dict): output={}
    submitted=bool(output.get("submitted"))
    status="SUBMITTED" if submitted else "MANUAL_ACTION_REQUIRED"
    return {
        "external_id":item.get("external_id"),
        "url":item.get("url"),
        "status":status,
        "submitted":submitted,
        "submission_attempted":bool(allow_submit),
        "reason":output.get("confirmation_text") if submitted else (output.get("blocker") or getattr(result,"failure_reason",None) or "Skyvern did not return positive submission confirmation."),
        "blockers":[] if submitted else [output.get("blocker")] if output.get("blocker") else [],
        "skyvern_run_id":getattr(result,"run_id",None),
        "skyvern_status":str(getattr(result,"status","")),
        "skyvern_recording_url":getattr(result,"recording_url",None),
        "final_url":output.get("final_url"),
    }

async def _run_async(queue_path: str, output: str, limit: int | None, allow_submit: bool):
    from skyvern import Skyvern
    # Default to the user's self-hosted Skyvern API. This keeps application
    # execution on the local machine and avoids Skyvern Cloud usage charges.
    base_url=os.getenv("SKYVERN_BASE_URL","http://localhost:8000")
    key=os.getenv("SKYVERN_API_KEY")
    if not key:
        raise RuntimeError("SKYVERN_API_KEY is required. Use the API key generated by your self-hosted Skyvern instance.")

    rows=json.loads((ROOT/queue_path).read_text(encoding="utf-8"))
    rows=[x for x in rows if x.get("status")=="READY_FOR_ATS_ADAPTER"]
    if limit is not None: rows=rows[:limit]
    profile=load_profile()
    client=Skyvern(api_key=key, base_url=base_url)
    results=[]
    for item in rows:
        try: results.append(await _run_one(client,item,profile,allow_submit))
        except Exception as exc:
            results.append({"external_id":item.get("external_id"),"url":item.get("url"),"status":"MANUAL_ACTION_REQUIRED","submitted":False,"submission_attempted":False,"reason":f"Skyvern execution failed: {type(exc).__name__}: {exc}","blockers":[]})
    out=ROOT/output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(results,indent=2),encoding="utf-8")
    return results

def run(queue_path="generated/application_queue.json", output="generated/skyvern_application_results.json", limit=None,
        headless=True, review_seconds=0, inspect_only=False, wait_for_human_seconds=0, allow_submit=False,
        before_submit=None, **_):
    """Compatibility entry point used by scheduled_runner.

    Skyvern owns browser execution. Legacy Playwright/provider arguments are accepted
    only so the discovery/resume scheduler does not need an ATS-specific interface.
    """
    if inspect_only:
        allow_submit=False
    # Skyvern performs the final action inside its autonomous task, so the old
    # selector-level before_submit callback cannot safely predict the click.
    return asyncio.run(_run_async(queue_path,output,limit,allow_submit))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--queue",default="generated/application_queue.json")
    p.add_argument("--output",default="generated/skyvern_application_results.json")
    p.add_argument("--limit",type=int)
    p.add_argument("--allow-submit",action="store_true")
    a=p.parse_args()
    print(json.dumps(run(a.queue,a.output,a.limit,allow_submit=a.allow_submit),indent=2))
