from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib import error, request

from app.cloud_policy import cloud_signal_counts, employer_cloud_modes
from app.master_resume import fixed_personal_facts, load_master_resume, master_tailoring_base
from app.resume_tailoring_policy import determine_tailoring_policy


SYSTEM_PROMPT = """You are an expert ATS resume writer for data engineering roles.

HYBRID MASTER/JD RULE — HARD CONSTRAINT:
- The user-uploaded master resume is the truthful base and factual technical reservoir.
- The current JD is the tailoring signal: it determines which master content should be emphasized, reordered, replaced, or supplemented.
- Do NOT rewrite the whole resume merely because a few JD targets exist.
- If the JD does not provide enough evidence to improve a section or bullet, retain the strong master content instead.
- A technology that is absent from the master may be added ONLY when the current JD/coverage plan supports it. Example: Kubernetes may be added when the JD requires Kubernetes.
- Never invent a technology that appears in neither the master nor the current JD/coverage plan.
- Unchanged master bullets should be copied verbatim. Existing user-authoritative metrics may remain only inside a verbatim retained master bullet.
- If you rewrite a master bullet, do not invent, transfer, alter, or manufacture numerical metrics/quantified outcomes.
- Preserve the master document's information density: two summary paragraphs, a substantial skills section, exactly 10 Fidelity bullets, 8 Cigna bullets, 8 Target bullets, and one Environment line per employer.
- The supplied tailoring-depth policy contains minimum counts of master bullets that must remain verbatim. These are retention floors, not rewrite quotas. Rewrite fewer bullets when fewer changes are needed.

SECTION BEHAVIOR:
- Professional Summary: start from the master summary, promote material JD themes, and keep approximately the same two-paragraph visual density. Do not shrink it into a keyword sentence.
- Technical Skills: start from the master skills inventory. Promote JD-required skills into appropriate categories, add JD-supported new technologies, and keep useful truthful master skills as supporting content. If space becomes excessive, remove the least relevant supporting master terms first. Do not add unsupported skills.
- Professional Experience: use the master bullets as the base. Rewrite only bullets that can credibly demonstrate material JD requirements; otherwise retain the original bullet verbatim. Keep each employer's domain coherent.
- Environment: use the master environment as the base, add JD-supported terms when useful, and remove/swap cloud-specific terms as required by the employer cloud policy.

EMPLOYER CLOUD CREDIBILITY RULE — HARD CONSTRAINT:
- Fidelity Investments must use exactly ONE cloud family in its experience bullets and Environment line.
- Select Fidelity's cloud from the JD's dominant cloud family: whichever of AWS, Azure, or GCP has the strongest/highest material provider/service signal in the current JD.
- If AWS is tied for strongest, use AWS as the credibility tie-breaker because it matches the master-backed Fidelity history.
- If only Azure and GCP are tied, use whichever tied family appears first in the JD.
- If the JD is cloud-neutral, Fidelity defaults to AWS only.
- If Fidelity's selected cloud differs from master AWS, rewrite/remove the master Fidelity cloud-specific bullets needed to eliminate the forbidden cloud. Do not mix cloud families.
- Cigna Healthcare is Azure-only. Never put AWS or GCP cloud services into Cigna experience. Cigna may retain Azure master evidence even when Azure is not named in the JD.
- Target Corporation is AWS-only. Never put Azure or GCP cloud services into Target experience. Target may retain AWS master evidence even when AWS is not named in the JD.
- Cross-cloud technologies such as Python, SQL, Spark, Databricks, Kafka, Airflow, Snowflake, Kubernetes, Terraform, and dbt do not by themselves select a cloud family.
- The global Technical Skills section may contain multiple cloud families when they are truthful master skills and/or genuinely requested by the JD. The single-cloud restriction applies to each employer's experience and Environment line.

GENERAL QUALITY RULES:
- Preserve fixed identity/history exactly: name, contact details, employer names, job titles, locations, employment dates, and education.
- Keep employer chronology fixed.
- Do not copy JD sentences verbatim. Convert JD requirements into natural data-engineering wording when a rewrite is justified.
- Do not invent certifications, degrees, employers, dates, locations, security clearances, team sizes, project names, or numerical outcomes.
- Avoid keyword stuffing and repetitive bullets.
- Use exact JD terminology when natural.
- Return valid JSON only.

Return this schema:
{
  "summary": "two paragraphs separated by \\n\\n",
  "skills": {"Professional Category": ["skill", "skill"]},
  "experience": [
    {"company": "Fidelity Investments", "bullets": [10 strings], "environment": "single-cloud-compliant environment"},
    {"company": "Cigna Healthcare", "bullets": [8 strings], "environment": "Azure-only environment"},
    {"company": "Target Corporation", "bullets": [8 strings], "environment": "AWS-only environment"}
  ],
  "education": "renderer preserves fixed education"
}
"""

CACHE_DIR = Path("generated") / "llm_resume_cache"


def _fixed_facts_for_prompt() -> dict:
    return fixed_personal_facts(load_master_resume())


def _master_base_for_prompt() -> dict:
    return master_tailoring_base(load_master_resume())


def build_prompt(job, profile=None, audit_feedback=None, coverage_plan=None):
    coverage_plan = coverage_plan or {}
    description = job.description or ""
    cloud_modes = employer_cloud_modes(description)
    tailoring_policy = determine_tailoring_policy(job, coverage_plan)
    prompt = {
        "task": "Create a hybrid JD-tailored resume using the uploaded master as the truthful base and the current JD as the tailoring signal.",
        "job": {
            "company": job.company,
            "title": job.title,
            "description": job.description,
        },
        "candidate_fixed_personal_history": _fixed_facts_for_prompt(),
        "authoritative_master_resume_base": _master_base_for_prompt(),
        "pre_generation_coverage_plan": coverage_plan,
        "tailoring_depth_policy": tailoring_policy,
        "employer_cloud_credibility_policy": {
            "hard_constraint": True,
            "jd_cloud_signal_counts": cloud_signal_counts(description),
            "selected_cloud_by_employer": cloud_modes,
            "fidelity_rule": "Use exactly one cloud family: the JD's strongest/highest cloud signal. AWS wins ties that include AWS; Azure/GCP-only ties use the first-mentioned tied cloud; cloud-neutral defaults to AWS.",
            "cigna_rule": "Azure only; never AWS or GCP in Cigna experience.",
            "target_rule": "AWS only; never Azure or GCP in Target experience.",
            "no_cloud_mixing_within_employer_experience": True,
            "global_skills_can_retain_truthful_master_clouds": True,
        },
        "technical_source_policy": {
            "allowed_technical_sources": ["authoritative_master_resume_base", "current_job_description"],
            "master_is_truthful_fallback_and_supporting_source": True,
            "new_technology_absent_from_master_requires_jd_evidence": True,
            "profile_argument_is_not_a_technical_source": True,
            "unchanged_master_metrics_allowed_only_in_verbatim_master_bullets": True,
            "rewritten_bullets_must_not_invent_or_move_metrics": True,
            "fixed_personal_history_must_be_preserved": True,
        },
        "layout_content_contract": {
            "summary_paragraphs": 2,
            "fidelity_bullets": 10,
            "cigna_bullets": 8,
            "target_bullets": 8,
            "environment_per_employer": True,
            "minimum_master_bullets_retained": tailoring_policy["minimum_master_bullets_retained"],
            "summary_min_master_density_ratio": tailoring_policy["summary_min_master_density_ratio"],
            "summary_max_master_density_ratio": tailoring_policy["summary_max_master_density_ratio"],
            "skills_min_master_row_ratio": tailoring_policy["skills_min_master_row_ratio"],
        },
        "quality_contract": {
            "cover_required_and_material_jd_targets": True,
            "use_exact_jd_terminology_when_natural": True,
            "no_keyword_stuffing": True,
            "no_invented_metrics": True,
            "no_invented_certifications": True,
            "no_invented_project_names": True,
            "no_unsupported_new_technologies": True,
            "retain_master_when_jd_cannot_improve_content": True,
            "fidelity_must_never_mix_cloud_families": True,
        },
    }
    if audit_feedback:
        prompt["revision_mode"] = True
        prompt["audit_feedback"] = audit_feedback
        prompt["task"] = (
            "Regenerate the hybrid resume for the same JD and correct every audit failure. Keep the uploaded master as the truthful base, "
            "do not exceed the allowed tailoring depth, preserve the required number of verbatim master bullets, obey the hard employer cloud modes, "
            "cover missing JD targets naturally, and do not invent new technologies or metrics."
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
