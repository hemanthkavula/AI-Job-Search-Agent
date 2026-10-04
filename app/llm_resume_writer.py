from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib import error, request

from app.cloud_policy import cloud_signal_counts, employer_cloud_modes
from app.master_resume import fixed_personal_facts, load_master_resume
from app.resume_tailoring_policy import determine_tailoring_policy

ROOT = Path(__file__).resolve().parents[1]
WORD_FORMAT_PATH = ROOT / "data" / "master_word_format.json"

EMPLOYER_DOMAIN_CONTEXT = {
    "Fidelity Investments": "financial services, trading, market data, investment risk, compliance, and portfolio analytics",
    "Cigna Healthcare": "healthcare claims, eligibility, provider/EHR data, clinical operations, privacy, and HIPAA-aware data handling",
    "Target Corporation": "retail sales, POS, e-commerce, inventory, product, merchandising, orders, and store operations",
}

SYSTEM_PROMPT = """You are an expert ATS resume writer for U.S. data engineering roles.

SOURCE-OF-TRUTH RULE — HARD CONSTRAINT:
- The uploaded Word/PDF resume is a FORMAT TEMPLATE ONLY for JD-tailored resumes.
- Do NOT copy or infer technical skills, technologies, architectures, technical bullets, environments, metrics, or accomplishments from that template.
- For every nonzero-target tailored resume, the CURRENT JOB DESCRIPTION and deterministic JD coverage plan are the only technical-content sources.
- Fixed personal/history facts are supplied separately and must be preserved exactly: name, contact details, employer names, job titles, locations, dates, and education.
- User-authorized employer domain context may be used to place JD responsibilities naturally: Fidelity = financial/trading; Cigna = healthcare; Target = retail.
- Employer cloud constraints are user rules, not permission to invent cloud services. If an allowed cloud is absent from the JD, use cloud-neutral JD content instead of adding unsupported services.
- Never introduce a technology, framework, platform, database, methodology, AI concept, or tool that is absent from the current JD/coverage plan.

JD-DRIVEN CONTENT RULES:
- Professional Summary: exactly 2 concise paragraphs. Use current-JD responsibilities and technologies only, plus fixed role/history facts. Keep the total length within the supplied Word content budget.
- Technical Skills: include only technologies/concepts explicitly supported by the current JD/coverage plan. Use clear ATS categories. Maximum 12 rows, maximum 7 terms per row, and stay within the supplied total-character budget. Prioritize required/material terms; do not reproduce a large generic master skill inventory.
- Professional Experience: preserve the fixed three employers, titles, locations, dates, and chronology. Write exactly 10 Fidelity bullets, 8 Cigna bullets, and 8 Target bullets. Translate the current JD into natural employer-domain bullets without copying JD sentences verbatim.
- Distribute JD requirements intelligently instead of repeating the same stack in every employer. Fidelity should carry the strongest/current JD coverage; Cigna and Target should support relevant JD concepts while remaining domain coherent.
- Each bullet must be concise and no more than the supplied maximum word count.
- Environment lines must contain only JD-supported technologies that are credible for that employer and must obey cloud constraints. Keep each Environment line within the supplied character budget.

NO-FABRICATION RULES — HARD CONSTRAINT:
- Do not invent or reuse numerical business outcomes, percentages, dataset volumes, event counts, latencies, member counts, throughput, cost savings, performance improvements, or other quantified accomplishments.
- Technology names that contain numbers (for example SCD Type 2, ADLS Gen2, Python 3) are allowed; quantified achievement claims are not.
- Do not invent certifications, degrees, employers, dates, locations, team sizes, security clearances, project names, customer names, or awards.
- Do not claim a technology just because it existed in the uploaded Word/PDF template. It must be in the current JD/coverage plan.
- Do not keyword-stuff. Use exact JD terminology when natural and write human-readable accomplishment/responsibility bullets without fabricated metrics.

EMPLOYER CLOUD CREDIBILITY RULE — HARD CONSTRAINT:
- Fidelity Investments must use at most ONE cloud family in its experience/environment. Select it from the JD's dominant cloud signal. AWS wins ties that include AWS; Azure/GCP-only ties use the first-mentioned tied cloud; cloud-neutral JDs default to an AWS credibility mode, but this does NOT authorize adding AWS technologies absent from the JD.
- Cigna Healthcare may use Azure cloud services only when those Azure services are supported by the JD. Never put AWS or GCP cloud services into Cigna experience/environment.
- Target Corporation may use AWS cloud services only when those AWS services are supported by the JD. Never put Azure or GCP cloud services into Target experience/environment.
- Cross-cloud technologies such as Python, SQL, Spark, Kafka, Airflow, Snowflake, Kubernetes, Terraform, Docker, dbt, and Databricks do not select a cloud family by themselves.
- The global Technical Skills section may include multiple cloud families only when each family is explicitly present in the current JD.

WORD-LAYOUT CONTENT BUDGET — HARD CONSTRAINT:
- The downstream renderer uses the user's exact Word font sizes, colors, margins, and spacing and will not shrink them to rescue oversized content.
- Keep the resume concise enough to render to exactly 2 pages.
- Obey the supplied limits for summary characters, skill rows/characters, bullet word count, and Environment length.

Return valid JSON only using this schema:
{
  "summary": "two paragraphs separated by \\n\\n",
  "skills": {"ATS Category": ["JD term", "JD term"]},
  "experience": [
    {"company": "Fidelity Investments", "bullets": [10 strings], "environment": "JD-supported, cloud-compliant technologies"},
    {"company": "Cigna Healthcare", "bullets": [8 strings], "environment": "JD-supported technologies; Azure cloud only if JD-supported"},
    {"company": "Target Corporation", "bullets": [8 strings], "environment": "JD-supported technologies; AWS cloud only if JD-supported"}
  ],
  "education": "renderer preserves fixed education"
}
"""

CACHE_DIR = Path("generated") / "llm_resume_cache"


def _fixed_facts_for_prompt() -> dict:
    return fixed_personal_facts(load_master_resume())


def _word_content_budget() -> dict:
    data = json.loads(WORD_FORMAT_PATH.read_text(encoding="utf-8"))
    return dict(data["content_budget"])


def build_prompt(job, profile=None, audit_feedback=None, coverage_plan=None):
    coverage_plan = coverage_plan or {}
    description = job.description or ""
    cloud_modes = employer_cloud_modes(description)
    tailoring_policy = determine_tailoring_policy(job, coverage_plan)
    budget = _word_content_budget()
    prompt = {
        "task": "Create a JD-driven resume. Use the uploaded Word resume only for layout downstream; do not use its technical content.",
        "job": {
            "company": job.company,
            "title": job.title,
            "description": job.description,
        },
        "candidate_fixed_personal_history": _fixed_facts_for_prompt(),
        "authorized_employer_domain_context": EMPLOYER_DOMAIN_CONTEXT,
        "pre_generation_coverage_plan": coverage_plan,
        "jd_evidence_depth_policy": tailoring_policy,
        "word_layout_content_budget": budget,
        "technical_source_policy": {
            "allowed_technical_sources": ["current_job_description", "pre_generation_coverage_plan"],
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
            "fidelity_rule": "At most one JD-supported cloud family in Fidelity. Dominant JD cloud wins; AWS wins ties including AWS; Azure/GCP ties use first mention. Cloud-neutral default is only a prohibition mode and does not authorize adding AWS terms.",
            "cigna_rule": "Never AWS/GCP in Cigna. Azure services may appear only when present in this JD; otherwise use cloud-neutral JD content.",
            "target_rule": "Never Azure/GCP in Target. AWS services may appear only when present in this JD; otherwise use cloud-neutral JD content.",
            "no_cloud_mixing_within_employer_experience": True,
        },
        "layout_content_contract": {
            "summary_paragraphs": 2,
            "fidelity_bullets": 10,
            "cigna_bullets": 8,
            "target_bullets": 8,
            "environment_per_employer": True,
            "summary_total_max_chars": budget["summary_total_max_chars"],
            "skills_max_rows": budget["skills_max_rows"],
            "skills_total_max_chars": budget["skills_total_max_chars"],
            "skills_max_terms_per_row": budget["skills_max_terms_per_row"],
            "bullet_max_words": budget["bullet_max_words"],
            "environment_max_chars": budget["environment_max_chars"],
            "required_pdf_pages": budget["pdf_pages_required"],
        },
        "quality_contract": {
            "cover_required_and_material_jd_targets": True,
            "use_exact_jd_terminology_when_natural": True,
            "no_keyword_stuffing": True,
            "no_invented_metrics": True,
            "no_reused_template_metrics": True,
            "no_invented_certifications": True,
            "no_invented_project_names": True,
            "no_technical_terms_absent_from_current_jd": True,
            "fidelity_must_never_mix_cloud_families": True,
            "domain_coherence_required": True,
        },
    }
    if audit_feedback:
        prompt["revision_mode"] = True
        prompt["audit_feedback"] = audit_feedback
        prompt["task"] = (
            "Regenerate the JD-driven resume for the same JD and correct every audit failure. "
            "Do not use technical content from the Word/PDF template. Preserve fixed history, use only current-JD technical content, "
            "cover missing JD targets naturally, obey employer domain/cloud rules, do not invent metrics, and remain within the exact two-page Word content budget."
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
