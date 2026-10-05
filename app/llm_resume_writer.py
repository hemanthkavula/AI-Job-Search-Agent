from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib import error, request

from app.cloud_policy import cloud_signal_counts, employer_cloud_modes
from app.master_resume import fixed_personal_facts, load_master_resume
from app.resume_tailoring_policy import determine_tailoring_policy

EMPLOYER_DOMAIN_CONTEXT = {
    "Fidelity Investments": "financial services, trading, market data, investment risk, compliance, and portfolio analytics",
    "Cigna Healthcare": "healthcare claims, eligibility, provider/EHR data, clinical operations, privacy, and HIPAA-aware data handling",
    "Target Corporation": "retail sales, POS, e-commerce, inventory, product, merchandising, orders, and store operations",
}

SYSTEM_PROMPT = """You are an expert ATS resume writer for U.S. data engineering roles.

SOURCE OF TRUTH:
- For a JD-tailored resume, the user's uploaded Word resume is the VISUAL FORMAT TEMPLATE and fixed-history source, not a technical-content whitelist.
- Preserve fixed candidate facts exactly: name/contact details, employer names, job titles, locations, employment dates, chronology, and education.
- Use the CURRENT JOB DESCRIPTION and deterministic JD coverage plan to drive the tailored Professional Summary, Technical Skills, experience emphasis, and Environment lines.
- Use the authorized employer-domain context naturally: Fidelity=financial/trading, Cigna=healthcare, Target=retail.

TAILORING:
- Professional Summary: use the same two-paragraph structure as the master Word resume. There is NO character-density target and NO page-count target.
- Technical Skills: organize JD-supported technologies/capabilities under clear market-standard technical categories. There is NO total-character budget. Do not omit an important JD-supported skill merely to keep the resume to two pages.
- Professional Experience: preserve the fixed three employers and chronology. Write exactly 10 Fidelity bullets, 8 Cigna bullets, and 8 Target bullets so the master's experience structure is preserved.
- Bullets must be meaningful, technically coherent, interview-defensible engineering statements tied to the current JD and the employer's business domain. Do not keyword-stuff.
- Environment lines should contain JD-supported technologies credible for that employer. There is NO character-length budget.
- Natural pagination is allowed. The finished resume may be 2, 3, or more pages depending on the content. Never shorten or delete material content solely to hit a page count.

NO FABRICATION:
- Never invent numerical outcomes, percentages, dataset volumes, event counts, latency bounds, cost savings, performance improvements, certifications, project names, customer names, team sizes, security clearances, employers, dates, or education.
- Technology names containing numbers such as SCD Type 2, ADLS Gen2, or Python 3 are allowed.
- Use exact JD terminology when natural, but do not create false specific accomplishments merely to place a keyword.

EMPLOYER CLOUD CREDIBILITY:
- Fidelity must use at most one cloud family in its experience/environment. Select the dominant cloud signaled by the JD; AWS wins ties containing AWS. For a cloud-neutral JD, remain cloud-neutral unless an allowed service is directly supported by the JD.
- Cigna may use Azure cloud services only when supported by the JD. Never place AWS or GCP cloud services in Cigna experience/environment.
- Target may use AWS cloud services only when supported by the JD. Never place Azure or GCP cloud services in Target experience/environment.
- Cross-cloud technologies such as Python, SQL, Spark, Kafka, Airflow, Snowflake, Kubernetes, Terraform, Docker, dbt, and Databricks do not by themselves select a cloud family.

FORMAT RULE:
- Preserve the master's visual structure downstream: section order, two summary paragraphs, Technical Skills rows, three employers, Roles & Responsibilities blocks, Environment lines, and education.
- Do NOT optimize for a fixed number of PDF pages, summary density ratio, Technical Skills character count, bullet word count, or Environment character count. Those are not user requirements.

Return valid JSON only using this schema:
{
  "summary": "two paragraphs separated by \\n\\n",
  "skills": {"ATS Category": ["JD-supported term", "JD-supported term"]},
  "experience": [
    {"company": "Fidelity Investments", "bullets": [10 strings], "environment": "JD-supported technologies"},
    {"company": "Cigna Healthcare", "bullets": [8 strings], "environment": "JD-supported technologies"},
    {"company": "Target Corporation", "bullets": [8 strings], "environment": "JD-supported technologies"}
  ],
  "education": "renderer preserves fixed education"
}
"""

CACHE_DIR = Path("generated") / "llm_resume_cache"


def _fixed_facts_for_prompt() -> dict:
    return fixed_personal_facts(load_master_resume())


def _sanitize_audit_feedback(audit_feedback):
    """Keep retries focused on real structural/factual problems, not scoring heuristics."""
    if not isinstance(audit_feedback, dict):
        return {}
    blocked = {
        "summary_density_ratio",
        "technical_skill_rows",
        "minimum_technical_skill_rows",
        "content_density_violations",
        "master_bullets_retained_by_employer",
        "master_retention_violations",
        "experience_depth_coverage",
        "experience_depth_gaps",
        "internal_ats_score",
        "human_quality_score",
        "readability_score",
        "repetition_score",
        "required_pdf_pages",
        "page_count",
    }
    safe = {key: value for key, value in audit_feedback.items() if key not in blocked}
    safe["retry_instruction"] = audit_feedback.get("retry_instruction") or (
        "Correct only factual or structural issues. Do not optimize for page count, density, "
        "character budgets, ATS score thresholds, or experience-depth thresholds."
    )
    return safe


def build_prompt(job, profile=None, audit_feedback=None, coverage_plan=None):
    coverage_plan = coverage_plan or {}
    description = job.description or ""
    cloud_modes = employer_cloud_modes(description)
    policy = determine_tailoring_policy(job, coverage_plan)
    prompt = {
        "task": (
            "Create a strong JD-specific data-engineering resume while preserving the user's "
            "fixed employment history. The Word master controls formatting downstream, not a page budget."
        ),
        "job": {
            "company": job.company,
            "title": job.title,
            "description": job.description,
        },
        "candidate_fixed_personal_history": _fixed_facts_for_prompt(),
        "authorized_employer_domain_context": EMPLOYER_DOMAIN_CONTEXT,
        "pre_generation_coverage_plan": coverage_plan,
        "jd_evidence_policy": {
            "mode": policy.get("mode"),
            "reason": policy.get("reason"),
            "richness": policy.get("richness"),
        },
        "technical_source_policy": {
            "allowed_technical_sources": [
                "current_job_description",
                "pre_generation_coverage_plan",
            ],
            "word_or_pdf_template_is_format_only": True,
            "template_technical_content_must_not_be_used": True,
            "profile_argument_is_not_a_technical_source": True,
            "every_technology_requires_current_jd_evidence": True,
            "fixed_personal_history_must_be_preserved": True,
            "employer_domain_context_is_context_only_not_a_technology_source": True,
        },
        "employer_cloud_credibility_policy": {
            "hard_constraint": True,
            "jd_cloud_signal_counts": cloud_signal_counts(description),
            "selected_cloud_by_employer": cloud_modes,
            "fidelity_rule": (
                "At most one JD-supported cloud family in Fidelity. Dominant JD cloud wins; "
                "AWS wins ties including AWS. Stay cloud-neutral if the JD does not support a service."
            ),
            "cigna_rule": (
                "Never AWS/GCP in Cigna. Azure services may appear only when present in this JD."
            ),
            "target_rule": (
                "Never Azure/GCP in Target. AWS services may appear only when present in this JD."
            ),
            "no_cloud_mixing_within_employer_experience": True,
        },
        "structure_contract": {
            "summary_paragraphs": 2,
            "fidelity_bullets": 10,
            "cigna_bullets": 8,
            "target_bullets": 8,
            "environment_per_employer": True,
            "natural_pagination": True,
            "fixed_page_count": None,
            "summary_density_threshold": None,
            "skills_character_budget": None,
            "bullet_word_budget": None,
            "environment_character_budget": None,
        },
        "quality_contract": {
            "cover_required_and_material_jd_targets": True,
            "use_exact_jd_terminology_when_natural": True,
            "no_keyword_stuffing": True,
            "no_invented_metrics": True,
            "no_invented_certifications": True,
            "no_invented_project_names": True,
            "no_technical_terms_absent_from_current_jd": True,
            "fidelity_must_never_mix_cloud_families": True,
            "domain_coherence_required": True,
            "page_count_never_drives_content": True,
        },
    }
    if audit_feedback:
        prompt["revision_mode"] = True
        prompt["audit_feedback"] = _sanitize_audit_feedback(audit_feedback)
        prompt["task"] = (
            "Regenerate the same JD-tailored resume and correct only the supplied structural/factual "
            "problem. Preserve all valid JD content and fixed history. Do not optimize for a fixed "
            "page count, summary density, Technical Skills length, or internal scoring threshold."
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
        with request.urlopen(req, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI API connection error: {exc.reason}") from exc

    text = _extract_output_text(payload)
    if not text:
        raise RuntimeError(
            f"OpenAI Responses API returned no output text: {json.dumps(payload)[:1200]}"
        )
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI returned non-JSON resume output: {text[:1200]}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("OpenAI returned a resume payload that is not a JSON object")
    _write_cache(cache_key, result)
    return result
