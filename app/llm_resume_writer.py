from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib import error, request

from app.cloud_policy import employer_cloud_modes
from app.master_resume import fixed_personal_facts, load_master_resume


SYSTEM_PROMPT = """You are an expert ATS resume writer for data engineering roles.

The CURRENT JOB DESCRIPTION is the primary technical-content source for a tailored resume.
The master resume is NOT a general technical whitelist or a source to freely copy. Do not copy or reuse its professional summary, technical skills, project descriptions, bullet wording, metrics, or accomplishments.

You receive only fixed personal/history facts from the master resume: name, contact details, employer names, job titles, locations, employment dates, and education. Preserve those fixed facts exactly.

EMPLOYER CLOUD CREDIBILITY RULE — HARD CONSTRAINT:
- Fidelity Investments must use exactly ONE cloud family in its generated experience and Environment line.
- If the JD contains exactly one cloud family, Fidelity uses that family only: AWS-only, Azure-only, or GCP-only.
- If the JD is multi-cloud (two or more cloud families are materially present), Fidelity uses AWS ONLY. Do not mix Azure or GCP into Fidelity merely because the JD is multi-cloud.
- If the JD is cloud-neutral, Fidelity defaults to AWS ONLY, matching the credible master history.
- Cigna Healthcare is Azure-only. Never put AWS or GCP cloud services into Cigna experience. If Azure is not relevant to the JD, use cloud-neutral JD-derived content rather than switching Cigna to another cloud.
- Target Corporation is AWS-only. Never put Azure or GCP cloud services into Target experience. If AWS is not relevant to the JD, use cloud-neutral JD-derived content rather than switching Target to another cloud.
- Cross-cloud technologies such as Python, SQL, Spark, Databricks, Kafka, Airflow, Snowflake, Kubernetes, Terraform, and dbt do not by themselves change the selected cloud family.
- The employer cloud rule is the only narrow exception to the JD-only technical-source rule: it may preserve the selected employer cloud family for credibility, but it must never be used to introduce a second cloud family into that employer's experience.

For every tailored resume:
- Generate the Professional Summary, Technical Skills, every Professional Experience bullet, and every Environment line from the CURRENT JOB DESCRIPTION and its coverage plan, subject to the employer cloud credibility rule above.
- Use exactly 10 Fidelity Investments bullets, 8 Cigna Healthcare bullets, and 8 Target Corporation bullets so the document preserves the master layout density.
- Keep each bullet concise, technically coherent, ATS-readable, and relevant to the JD.
- Do not copy JD sentences verbatim. Convert requirements into natural data-engineering responsibilities and implementation statements.
- Do not invent certifications, degrees, employers, dates, locations, security clearances, team sizes, project names, numerical metrics, or quantified outcomes.
- Do not turn a number mentioned in the JD into a claimed candidate accomplishment.
- Outside the employer cloud credibility exception, do not introduce a technology, platform, programming language, cloud service, database, tool, methodology, or technical concept unless it appears in the JD or supplied coverage plan.
- Do not use technologies from the master resume simply because they may be familiar or plausible.
- Keep the employer chronology fixed. Technical emphasis may differ by employer, but all non-cloud technical content must still come from the same current JD.
- Avoid keyword stuffing. Important required/material JD terms must appear naturally in Technical Skills and, where appropriate, in Professional Experience.
- Use two concise summary paragraphs separated by a blank line.
- Build Technical Skills using professional functional categories and JD-derived terms. Technical Skills may reflect all cloud families genuinely requested by the JD; the single-cloud restriction applies to each employer's EXPERIENCE and Environment line, not to the global skills inventory.
- Every experience object must include an Environment string containing technologies/capabilities actually used in that employer's generated bullets and must obey that employer's selected cloud family.
- Return valid JSON only.

Return this schema:
{
  "summary": "two concise paragraphs separated by \\n\\n",
  "skills": {"Professional Category": ["JD-derived term", "JD-derived term"]},
  "experience": [
    {"company": "Fidelity Investments", "bullets": [10 strings], "environment": "technologies/capabilities obeying Fidelity cloud mode"},
    {"company": "Cigna Healthcare", "bullets": [8 strings], "environment": "Azure-only or cloud-neutral technologies/capabilities"},
    {"company": "Target Corporation", "bullets": [8 strings], "environment": "AWS-only or cloud-neutral technologies/capabilities"}
  ],
  "education": "preserve fixed education; renderer will use fixed facts"
}
"""

CACHE_DIR = Path("generated") / "llm_resume_cache"


def _fixed_facts_for_prompt() -> dict:
    """Return personal/history facts only; intentionally excludes general master technical content."""
    return fixed_personal_facts(load_master_resume())


def build_prompt(job, profile=None, audit_feedback=None, coverage_plan=None):
    coverage_plan = coverage_plan or {}
    cloud_modes = employer_cloud_modes(job.description or "")
    prompt = {
        "task": "Create a JD-specific resume using the job description as the primary technical source while obeying the hard employer cloud credibility policy.",
        "job": {
            "company": job.company,
            "title": job.title,
            "description": job.description,
        },
        "candidate_fixed_personal_history_only": _fixed_facts_for_prompt(),
        "pre_generation_coverage_plan": coverage_plan,
        "employer_cloud_credibility_policy": {
            "hard_constraint": True,
            "selected_cloud_by_employer": cloud_modes,
            "fidelity_rule": "Exactly one JD cloud -> that cloud only. Multi-cloud or cloud-neutral JD -> AWS only.",
            "cigna_rule": "Azure only; never AWS or GCP in Cigna experience.",
            "target_rule": "AWS only; never Azure or GCP in Target experience.",
            "no_cloud_mixing_within_employer_experience": True,
            "global_skills_may_list_all_jd_clouds": True,
        },
        "technical_source_policy": {
            "job_description_is_primary_technical_source": True,
            "employer_cloud_credibility_exception_only": True,
            "master_summary_forbidden": True,
            "master_skills_forbidden_as_general_source": True,
            "master_experience_bullets_forbidden": True,
            "master_metrics_forbidden": True,
            "fixed_personal_history_must_be_preserved": True,
        },
        "layout_content_contract": {
            "summary_paragraphs": 2,
            "fidelity_bullets": 10,
            "cigna_bullets": 8,
            "target_bullets": 8,
            "environment_per_employer": True,
            "environment_must_obey_employer_cloud_mode": True,
        },
        "quality_contract": {
            "cover_all_required_and_material_targets": True,
            "use_exact_jd_terminology_when_natural": True,
            "no_keyword_stuffing": True,
            "no_invented_metrics": True,
            "no_invented_certifications": True,
            "no_invented_project_names": True,
            "no_unlisted_technical_terms_except_selected_employer_cloud_family": True,
            "professional_experience_must_demonstrate_jd_requirements": True,
            "fidelity_must_never_mix_cloud_families": True,
        },
    }
    if audit_feedback:
        prompt["revision_mode"] = True
        prompt["audit_feedback"] = audit_feedback
        prompt["task"] = (
            "Regenerate for the same JD and correct every audit failure. Obey the hard employer cloud modes, "
            "never mix cloud families within Fidelity/Cigna/Target experience, preserve fixed personal/history facts, "
            "and do not introduce non-cloud technical content absent from the current JD/coverage plan."
        )
    return prompt


def _extract_output_text(payload):
    if payload.get("output_text"):
        return payload["output_text"]
    chunks = []
    for item in payload.get("output", []):
        for part in item.get("content", []):
            if part.get("type") == "output_text" and part.get("text"):
                chunks.append(part["text"])
    return "".join(chunks)


def _cache_key(model, prompt):
    payload = json.dumps(
        {"model": model, "instructions": SYSTEM_PROMPT, "prompt": prompt},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_cache(cache_key):
    path = CACHE_DIR / f"{cache_key}.json"
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _write_cache(cache_key, value):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{cache_key}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def generate_with_llm(job, profile=None, audit_feedback=None, coverage_plan=None):
    key = os.getenv("OPENAI_API_KEY") or os.getenv("RESUME_LLM_API_KEY")
    if not key:
        return None
    endpoint = os.getenv("RESUME_LLM_ENDPOINT", "https://api.openai.com/v1/responses")
    model = os.getenv("RESUME_LLM_MODEL", "gpt-5.6")
    prompt = build_prompt(job, profile, audit_feedback, coverage_plan)
    cache_key = _cache_key(model, prompt)
    cached = _read_cache(cache_key)
    if cached is not None:
        print(f"Resume LLM cache HIT | {cache_key[:12]} | API call skipped", flush=True)
        return cached

    print(f"Resume LLM cache MISS | {cache_key[:12]} | calling API", flush=True)
    body = json.dumps(
        {
            "model": model,
            "instructions": SYSTEM_PROMPT,
            "input": json.dumps(prompt),
            "max_output_tokens": 14000,
        }
    ).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI API connection error: {exc.reason}") from exc

    text = _extract_output_text(payload)
    if not text:
        raise RuntimeError(f"OpenAI Responses API returned no output text: {json.dumps(payload)[:1200]}")
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI returned non-JSON resume output: {text[:1200]}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("OpenAI returned a resume payload that is not a JSON object")
    _write_cache(cache_key, result)
    return result
