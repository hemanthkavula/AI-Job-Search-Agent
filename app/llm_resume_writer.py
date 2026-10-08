from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
from urllib import error, request

from app.cloud_policy import (
    CLOUD_AWS,
    CLOUD_AZURE,
    CLOUD_GCP,
    cloud_signal_counts,
    detect_cloud_families,
    employer_cloud_modes,
)
from app.master_resume import experience_bullet_counts, fixed_personal_facts, load_master_resume
from app.resume_tailoring_policy import determine_tailoring_policy

EMPLOYER_DOMAIN_CONTEXT = {
    "Fidelity Investments": "financial services, trading, market data, investment risk, compliance, and portfolio analytics",
    "Cigna Healthcare": "healthcare claims, eligibility, provider/EHR data, clinical operations, privacy, and HIPAA-aware data handling",
    "Target Corporation": "retail sales, POS, e-commerce, inventory, product, merchandising, orders, and store operations",
}

OLDER_EMPLOYERS = {"Cigna Healthcare", "Target Corporation"}

# User rule: AI-era technologies belong only in the current Fidelity experience.
# Cigna (2022-2023) and Target (2020-2021) must never be retrofitted with them.
OLDER_EMPLOYER_AI_PATTERN = re.compile(
    r"(?i)(?:\bartificial intelligence\b|\bAI/ML\b|\bgenerative AI\b|\bgenAI\b|"
    r"\blarge language models?\b|\bLLMs?\b|\bretrieval[- ]augmented generation\b|\bRAG\b|"
    r"\bvector stores?\b|\bvector search\b|\bembeddings?\b|\bMLOps\b|\bmodel serving\b|"
    r"\bmodel inference\b|\bfeature stores?\b|\bClaude\b|\bCursor\b)"
)

CLOUD_SERVICE_CATALOG = {
    CLOUD_AWS: (
        ("AWS", r"\baws\b|amazon web services"),
        ("AWS Glue", r"\baws glue\b|\bglue\b"),
        ("Amazon S3", r"\bamazon s3\b|\bs3\b"),
        ("Amazon EMR", r"\bamazon emr\b|\bemr\b"),
        ("Amazon Redshift", r"\bamazon redshift\b|\bredshift\b"),
        ("AWS Lambda", r"\baws lambda\b|\blambda\b"),
        ("Amazon Kinesis", r"\bamazon kinesis\b|\bkinesis\b"),
        ("AWS Step Functions", r"\baws step functions?\b|\bstep functions?\b"),
        ("Amazon Athena", r"\bamazon athena\b|\bathena\b"),
        ("Amazon DynamoDB", r"\bamazon dynamodb\b|\bdynamodb\b"),
        ("Amazon ECS", r"\bamazon ecs\b|\becs\b"),
        ("Amazon EKS", r"\bamazon eks\b|\beks\b"),
        ("AWS Lake Formation", r"\b(?:aws )?lake formation\b"),
    ),
    CLOUD_AZURE: (
        ("Microsoft Azure", r"\bmicrosoft azure\b|\bazure\b"),
        ("Azure Data Factory", r"\bazure data factory\b|\badf\b"),
        ("Azure Synapse Analytics", r"\bazure synapse(?: analytics)?\b|\bsynapse analytics\b"),
        ("ADLS Gen2", r"\badls(?:\s*gen\s*2)?\b|azure data lake storage(?: gen2)?"),
        ("Azure Event Hubs", r"\bazure event hubs?\b|\bevent hubs?\b"),
        ("Azure Functions", r"\bazure functions?\b"),
        ("Microsoft Purview", r"\b(?:azure|microsoft) purview\b|\bpurview\b"),
        ("Azure Stream Analytics", r"\bazure stream analytics\b"),
        ("Azure Data Explorer", r"\bazure data explorer\b"),
        ("Azure Blob Storage", r"\bazure blob storage\b|\bblob storage\b"),
    ),
    CLOUD_GCP: (
        ("Google Cloud Platform (GCP)", r"\bgcp\b|google cloud(?: platform)?"),
        ("BigQuery", r"\bbigquery\b|google bigquery"),
        ("Google Cloud Storage (GCS)", r"google cloud storage|\bgcs\b"),
        ("Dataflow", r"\bdataflow\b"),
        ("Pub/Sub", r"\bpub\s*/?\s*sub\b|\bpubsub\b"),
        ("Dataproc", r"\bdataproc\b"),
        ("Cloud Composer", r"\bcloud composer\b"),
        ("Cloud Functions", r"\bgoogle cloud functions?\b|\bcloud functions?\b"),
        ("Cloud Run", r"\bcloud run\b"),
        ("Dataplex", r"\bdataplex\b"),
        ("BigLake", r"\bbiglake\b"),
        ("Cloud SQL", r"\bcloud sql\b"),
        ("Cloud Spanner", r"\b(?:cloud )?spanner\b"),
    ),
}

TECH_ALIASES = {
    "Python": ("python",),
    "SQL": ("sql",),
    "Scala": ("scala",),
    "PySpark": ("pyspark",),
    "Apache Spark": ("apache spark", "spark"),
    "Databricks": ("databricks",),
    "Delta Lake": ("delta lake",),
    "Apache Kafka": ("apache kafka", "kafka"),
    "Snowflake": ("snowflake",),
    "Apache Airflow": ("apache airflow", "airflow"),
    "Airflow": ("apache airflow", "airflow"),
    "dbt": ("dbt",),
    "Terraform": ("terraform",),
    "Docker": ("docker",),
    "Jenkins": ("jenkins",),
    "GitLab CI/CD": ("gitlab ci/cd", "gitlab"),
    "Git": ("git",),
    "Great Expectations": ("great expectations",),
    "Power BI": ("power bi",),
    "Tableau": ("tableau",),
    "Looker": ("looker",),
    "Oracle": ("oracle",),
    "SQL Server": ("sql server",),
    "PostgreSQL": ("postgresql", "postgres"),
    "MySQL": ("mysql",),
    "MongoDB": ("mongodb",),
    "DynamoDB": ("dynamodb",),
    "Amazon DynamoDB": ("amazon dynamodb", "dynamodb"),
    "AWS Glue": ("aws glue", "glue"),
    "Amazon EMR": ("amazon emr", "emr"),
    "Amazon S3": ("amazon s3", "s3"),
    "Amazon Redshift": ("amazon redshift", "redshift"),
    "Lambda": ("aws lambda", "lambda"),
    "AWS Lambda": ("aws lambda", "lambda"),
    "Kinesis": ("amazon kinesis", "kinesis"),
    "Amazon Kinesis": ("amazon kinesis", "kinesis"),
    "Data Factory": ("azure data factory", "data factory", "adf"),
    "Azure Data Factory": ("azure data factory", "data factory", "adf"),
    "Synapse Analytics": ("azure synapse analytics", "azure synapse", "synapse analytics"),
    "Azure Synapse Analytics": ("azure synapse analytics", "azure synapse", "synapse analytics"),
    "Azure Data Lake Storage Gen2": ("azure data lake storage gen2", "adls gen2", "adls"),
    "ADLS Gen2": ("azure data lake storage gen2", "adls gen2", "adls"),
    "Event Hub": ("azure event hub", "azure event hubs", "event hub", "event hubs"),
    "Azure Event Hubs": ("azure event hub", "azure event hubs", "event hub", "event hubs"),
    "Azure Purview": ("azure purview", "microsoft purview", "purview"),
    "Microsoft Purview": ("azure purview", "microsoft purview", "purview"),
    "Star Schema": ("star schema",),
    "Snowflake Schema": ("snowflake schema",),
    "Dimensional Modeling": ("dimensional modeling",),
    "Slowly Changing Dimensions": ("slowly changing dimensions", "scd type 2", "scd"),
}

for _cloud_rows in CLOUD_SERVICE_CATALOG.values():
    for _label, _pattern in _cloud_rows:
        TECH_ALIASES.setdefault(_label, tuple())

SYSTEM_PROMPT = """You are an expert ATS resume writer for U.S. data engineering roles.

SOURCE OF TRUTH:
- The user's uploaded master resume is the VISUAL FORMAT AUTHORITY and the historical technology baseline.
- Preserve fixed candidate facts exactly: name/contact details, employer names, job titles, locations, employment dates, chronology, and education.
- Fidelity Investments is the current employer and is the primary JD-tailored section.
- Cigna Healthcare and Target Corporation are historical employers. Their master-resume technology stacks are authoritative historical boundaries.
- Use the authorized employer-domain context naturally: Fidelity=financial/trading, Cigna=healthcare, Target=retail.

TAILORING PRIORITY:
1. FIDELITY INVESTMENTS — fully JD-adaptive while remaining truthful and financial-domain coherent.
   - Select ONE cloud family from the JD: AWS, Azure, or GCP, using the supplied deterministic cloud selection.
   - New tools/services absent from the master may be added to Fidelity only when the current JD explicitly supports them.
   - AI/GenAI/LLM/RAG/vector/MLOps technologies may appear in Fidelity only when relevant to the current JD.
2. CIGNA HEALTHCARE — Azure historical baseline from the master resume.
   - Bullets MAY be rewritten for semantic JD alignment when useful; they do not have to remain verbatim.
   - Any technology mentioned in a rewritten Cigna bullet must already be supported by Cigna's master-backed historical stack and must be plausible for the Jan 2022-Dec 2023 employment period.
   - Never add AWS or GCP services.
   - Never add AI/GenAI/LLM/RAG/vector stores/vector search/embeddings/MLOps/feature-store/model-inference technologies.
3. TARGET CORPORATION — AWS historical baseline from the master resume.
   - Bullets MAY be rewritten for semantic JD alignment when useful; they do not have to remain verbatim.
   - Any technology mentioned in a rewritten Target bullet must already be supported by Target's master-backed historical stack and must be plausible for the Jan 2020-Dec 2021 employment period.
   - Never add Azure or GCP services.
   - Never add AI/GenAI/LLM/RAG/vector stores/vector search/embeddings/MLOps/feature-store/model-inference technologies.

TECHNICAL SKILLS:
- The TECHNICAL SKILLS section and row styling are fixed, but the LLM owns the category taxonomy for tailored resumes.
- Category names MAY be renamed, merged, split, reordered, or newly created when doing so improves alignment with the current JD and remains ATS-readable.
- Add relevant JD-supported skills to the most appropriate category. Create a new category when the JD contains a meaningful skill family that does not fit the existing taxonomy.
- Do not create redundant or near-duplicate categories. Prefer concise category labels that a recruiter would immediately understand.
- Build Technical Skills from the COMPLETE FINAL RESUME after all employer bullets are finalized, not from the JD-selected cloud alone.
- Preserve technologies credibly evidenced across all employers. If Fidelity is GCP-aligned, Cigna still contributes its Azure skills and Target still contributes its AWS skills to Technical Skills.
- If Fidelity's selected cloud is GCP, include a GCP-focused category containing only GCP services actually supported by the JD, while retaining historically supported AWS and Azure categories from Target and Cigna.
- New JD-supported technologies may appear only where allowed by the employer-history and cloud credibility rules.
- Keep each row concise and ATS-readable. Do not create paragraph-like skill rows.

PROFESSIONAL SUMMARY:
- Write ONE substantial prose paragraph, never bullets, fragments, labels, or short point-like statements.
- Target roughly 100-140 words with 4-6 complete sentences.
- Cover seniority and years of experience, domain breadth, core data-engineering strengths, the most relevant JD-aligned technologies, architecture/platform depth, data modeling/quality/governance/performance strengths, and current Fidelity scope.
- Include AI/ML exposure only when it is relevant and supported, and only in the current Fidelity context.
- Use the master summary as the baseline level of substance. A tailored summary must not be materially thinner than the master summary.
- Keep it information-dense and natural; do not keyword-stuff or invent metrics.

WHOLE-RESUME JD ALIGNMENT:
- Treat the Professional Summary, Technical Skills, Fidelity experience, and permitted historical-experience wording as one coordinated JD-tailoring problem.
- Material JD requirements should be reflected in the most credible section(s), not dumped into Technical Skills only.
- If a required technology is added to Technical Skills, use it in Fidelity experience when the JD supports it and the experience remains truthful and interview-defensible.
- Avoid contradictions where the skills section claims a technology that is unsupported by the tailored experience or the allowed historical baseline.
- Prioritize the JD's required skills, responsibilities, architecture patterns, data-platform concepts, and domain language while preserving all factual/history constraints.

PROFESSIONAL EXPERIENCE:
- Preserve exactly the employer bullet counts supplied in structure_contract from the current master resume.
- One bullet = one concise engineering sentence. Keep the length close to the corresponding master bullet; do not turn bullets into paragraphs.
- Bullets must be meaningful, technically coherent, interview-defensible, and tied to the employer's real business domain.
- Do not keyword-stuff.
- After each employer, return skills_used as a list of ONLY the concrete technologies/tools that are actually named in that employer's final bullets. No prose, responsibilities, capabilities, or generic phrases.

NO FABRICATION:
- Never invent numerical outcomes, percentages, dataset volumes, event counts, latency bounds, cost savings, performance improvements, certifications, project names, customer names, team sizes, security clearances, employers, dates, or education.
- Existing master-resume metrics may remain only when the corresponding master bullet is retained verbatim.
- Technology names containing numbers such as SCD Type 2 or ADLS Gen2 are allowed.

FORMAT / LAYOUT:
- Preserve the master's visual structure downstream except for the approved summary update: render one substantial Professional Summary paragraph, then Technical Skills rows, three employers, compact Environment technology-only lines, and education.
- Do not create prose Environment paragraphs. The renderer will display a compact Environment: technology-only line after each employer.
- Keep the resume visually close to the master: one substantial summary paragraph, concise skills rows, compact bullets, no artificial page breaks, no bloated extra page.

Return valid JSON only using this schema:
{
  "summary": "one substantial 100-140 word prose paragraph",
  "skills": {"ATS Category": ["technical skill", "technical skill"]},
  "experience": [
    {"company": "Fidelity Investments", "bullets": ["exactly structure_contract.fidelity_bullets strings"], "skills_used": ["technology", "technology"]},
    {"company": "Cigna Healthcare", "bullets": ["exactly structure_contract.cigna_bullets strings"], "skills_used": ["technology", "technology"]},
    {"company": "Target Corporation", "bullets": ["exactly structure_contract.target_bullets strings"], "skills_used": ["technology", "technology"]}
  ],
  "education": "renderer preserves fixed education"
}
"""

CACHE_DIR = Path("generated") / "llm_resume_cache"


def _fixed_facts_for_prompt() -> dict:
    return fixed_personal_facts(load_master_resume())


def _master_technical_baseline() -> dict:
    master = load_master_resume()
    return {
        "skills": {key: list(values) for key, values in master["skills"].items()},
        "experience": [
            {
                "company": row["company"],
                "bullets": list(row["bullets"]),
                "historical_skills": row.get("environment", ""),
            }
            for row in master["experience"]
        ],
    }


def _sanitize_audit_feedback(audit_feedback):
    if not isinstance(audit_feedback, dict):
        return {}
    blocked = {
        "summary_density_ratio",
        "technical_skill_rows",
        "minimum_technical_skill_rows",
        "content_density_violations",
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
        "Correct only factual, historical-credibility, cloud, or structural issues. Keep Fidelity JD-adaptive; "
        "keep Cigna Azure/master-backed and Target AWS/master-backed; never put AI-era technologies in Cigna or Target."
    )
    return safe


def build_prompt(job, profile=None, audit_feedback=None, coverage_plan=None):
    coverage_plan = coverage_plan or {}
    description = job.description or ""
    cloud_modes = employer_cloud_modes(description)
    policy = determine_tailoring_policy(job, coverage_plan)
    prompt = {
        "task": (
            "Create a strong JD-specific data-engineering resume. Tailor Fidelity primarily, preserve historically credible "
            "Cigna/Target baselines, and keep the master Word layout compact."
        ),
        "job": {
            "company": job.company,
            "title": job.title,
            "description": job.description,
        },
        "candidate_fixed_personal_history": _fixed_facts_for_prompt(),
        "master_resume_technical_baseline": _master_technical_baseline(),
        "authorized_employer_domain_context": EMPLOYER_DOMAIN_CONTEXT,
        "pre_generation_coverage_plan": coverage_plan,
        "jd_evidence_policy": {
            "mode": policy.get("mode"),
            "reason": policy.get("reason"),
            "richness": policy.get("richness"),
        },
        "technical_source_policy": {
            "fidelity_sources": ["master_resume_baseline", "current_job_description", "pre_generation_coverage_plan"],
            "cigna_source": "master_resume_historical_whitelist_with_semantic_jd_alignment",
            "target_source": "master_resume_historical_whitelist_with_semantic_jd_alignment",
            "new_technology_allowed_only_in_fidelity_when_jd_supported": True,
            "fixed_personal_history_must_be_preserved": True,
        },
        "employer_cloud_credibility_policy": {
            "hard_constraint": True,
            "jd_cloud_signal_counts": cloud_signal_counts(description),
            "selected_cloud_by_employer": cloud_modes,
            "fidelity_rule": "Use only the selected JD cloud family in Fidelity experience; new JD-supported services are allowed there.",
            "cigna_rule": "Azure baseline only; never AWS/GCP; do not add technologies outside the master-backed Cigna stack.",
            "target_rule": "AWS baseline only; never Azure/GCP; do not add technologies outside the master-backed Target stack.",
            "no_cloud_mixing_within_employer_experience": True,
        },
        "historical_timeline_policy": {
            "hard_constraint": True,
            "cigna_dates": "Jan 2022 - Dec 2023",
            "target_dates": "Jan 2020 - Dec 2021",
            "forbid_ai_era_technology_in_cigna_and_target": True,
            "older_employer_new_technology_requires_master_backing": True,
            "cigna_employment_window": "Jan 2022-Dec 2023",
            "target_employment_window": "Jan 2020-Dec 2021",
            "reject_technology_that_is_not_plausible_for_employer_period": True,
            "forbidden_examples": [
                "Generative AI", "LLM", "RAG", "vector stores", "vector search", "embeddings",
                "MLOps", "feature stores", "model inference", "Claude", "Cursor"
            ],
        },
        "skills_policy": {
            "category_names_are_jd_adaptive": True,
            "allow_category_rename_merge_split_reorder": True,
            "allow_new_categories_when_jd_supported": True,
            "technical_skills_must_reflect_entire_final_resume": True,
            "preserve_historical_cloud_skills_from_all_employers": True,
            "build_skills_after_final_experience_reconciliation": True,
            "add_gcp_category_when_fidelity_selects_gcp": cloud_modes.get("Fidelity Investments") == CLOUD_GCP,
            "new_fidelity_jd_tools_may_be_added": True,
            "avoid_redundant_categories": True,
            "employer_footer_is_environment_technology_only": True,
        },
        "structure_contract": {
            "summary_paragraphs": 1,
            "summary_min_words": 95,
            "summary_target_words": "100-140",
            "summary_min_sentences": 4,
            "summary_max_sentences": 6,
            "summary_style": "substantial_prose_paragraph_not_bullets_or_fragments",
            "fidelity_bullets": experience_bullet_counts().get("Fidelity Investments", 0),
            "cigna_bullets": experience_bullet_counts().get("Cigna Healthcare", 0),
            "target_bullets": experience_bullet_counts().get("Target Corporation", 0),
            "employer_footer_label": "Environment",
            "environment_paragraphs": False,
            "compact_master_like_layout": True,
        },
        "quality_contract": {
            "cover_required_and_material_jd_targets_primarily_in_fidelity": True,
            "use_exact_jd_terminology_when_natural": True,
            "no_keyword_stuffing": True,
            "no_invented_metrics": True,
            "no_invented_certifications": True,
            "no_invented_project_names": True,
            "fidelity_must_never_mix_cloud_families": True,
            "domain_coherence_required": True,
            "historical_technology_credibility_required": True,
            "technical_skills_taxonomy_should_match_jd": True,
            "technical_skills_should_cover_material_jd_terms": True,
            "summary_skills_and_experience_must_be_coherent": True,
            "material_jd_requirements_should_map_to_credible_resume_evidence": True,
        },
    }
    if audit_feedback:
        prompt["revision_mode"] = True
        prompt["audit_feedback"] = _sanitize_audit_feedback(audit_feedback)
        prompt["task"] = (
            "Regenerate the same resume and correct the supplied factual/historical/cloud/structural issue. "
            "Preserve valid Fidelity JD alignment and the master-backed Cigna/Target history."
        )
    return prompt


def _merge_unique(*groups):
    out = []
    seen = set()
    for group in groups:
        for value in group or []:
            text = str(value).strip()
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                out.append(text)
    return out


_TECH_CANONICAL_LABELS = {
    "spark": "Apache Spark",
    "kafka": "Apache Kafka",
    "airflow": "Apache Airflow",
    "dynamodb": "Amazon DynamoDB",
    "lambda": "AWS Lambda",
    "aws lambda": "AWS Lambda",
    "kinesis": "Amazon Kinesis",
    "amazon kinesis": "Amazon Kinesis",
    "glue": "AWS Glue",
    "emr": "Amazon EMR",
    "s3": "Amazon S3",
    "redshift": "Amazon Redshift",
    "data factory": "Azure Data Factory",
    "adf": "Azure Data Factory",
    "synapse": "Azure Synapse Analytics",
    "synapse analytics": "Azure Synapse Analytics",
    "azure synapse": "Azure Synapse Analytics",
    "azure data lake storage gen2": "ADLS Gen2",
    "azure data lake storage": "ADLS Gen2",
    "adls": "ADLS Gen2",
    "event hub": "Azure Event Hubs",
    "azure event hub": "Azure Event Hubs",
    "purview": "Microsoft Purview",
    "azure purview": "Microsoft Purview",
}


def _canonical_technology_label(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return _TECH_CANONICAL_LABELS.get(text.casefold(), text)


def _merge_unique_technologies(*groups):
    out = []
    seen = set()
    for group in groups:
        for value in group or []:
            text = _canonical_technology_label(value)
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                out.append(text)
    return out


def _jd_cloud_services(description: str, cloud: str) -> list[str]:
    out = []
    for label, pattern in CLOUD_SERVICE_CATALOG.get(cloud, ()):
        if re.search(pattern, description or "", flags=re.I):
            out.append(label)
    return out


def _category_matches(category: str, family: str) -> bool:
    low = str(category or "").casefold()
    if family == "programming":
        return any(token in low for token in ("programming", "language", "coding", "query"))
    if family == CLOUD_AWS:
        return "aws" in low or "amazon" in low
    if family == CLOUD_AZURE:
        return "azure" in low or "microsoft cloud" in low
    if family == CLOUD_GCP:
        return "gcp" in low or "google cloud" in low
    return False


def _find_category(out: dict, family: str):
    return next((name for name in out if _category_matches(name, family)), None)


def _normalize_skills(raw_skills, description: str) -> dict:
    master = load_master_resume()
    master_skills = master["skills"]
    source = raw_skills if isinstance(raw_skills, dict) else {}
    selected = employer_cloud_modes(description).get("Fidelity Investments", CLOUD_AWS)

    # Preserve the LLM's JD-adaptive category taxonomy and ordering.
    out = {}
    for category, values in source.items():
        name = re.sub(r"\s+", " ", str(category or "")).strip().strip(":")
        compact = _merge_unique_technologies(values)[:12]
        if not name or not compact:
            continue
        # Avoid duplicate category labels that differ only by case.
        existing = next((key for key in out if key.casefold() == name.casefold()), None)
        if existing:
            out[existing] = _merge_unique_technologies(out[existing], compact)[:12]
        else:
            out[name] = compact

    # If the LLM returned nothing useful, fall back to the master taxonomy.
    if not out:
        out = {
            str(category): list(values)
            for category, values in master_skills.items()
            if values
        }

    # Always preserve programming plus the historically supported cloud baselines
    # from the complete resume. The JD controls Fidelity's current-employer cloud,
    # but must never erase real Azure/AWS experience from Cigna/Target in the top
    # Technical Skills section.
    programming = list(master_skills.get("Programming Languages", []))
    if programming:
        category = _find_category(out, "programming") or "Programming Languages"
        out.setdefault(category, [])
        out[category] = _merge_unique_technologies(out[category], programming)[:12]

    for family, master_key, fallback_name in (
        (CLOUD_AWS, "Cloud Platforms (AWS)", "Cloud Platforms (AWS)"),
        (CLOUD_AZURE, "Cloud Platforms (Azure)", "Cloud Platforms (Azure)"),
    ):
        baseline = list(master_skills.get(master_key, []))
        category = _find_category(out, family) or fallback_name
        out.setdefault(category, [])
        additions = baseline
        if selected == family:
            additions = _merge_unique(additions, _jd_cloud_services(description, family))
        out[category] = _merge_unique_technologies(out[category], additions)[:12]

    # GCP is added when supported by the JD/final Fidelity experience. Unlike AWS
    # and Azure, it is not a fixed historical baseline for Cigna/Target.
    if selected == CLOUD_GCP or _find_category(out, CLOUD_GCP):
        category = _find_category(out, CLOUD_GCP) or "Cloud Platforms (GCP)"
        out.setdefault(category, [])
        gcp_values = _jd_cloud_services(description, CLOUD_GCP)
        if selected == CLOUD_GCP and not gcp_values:
            gcp_values = ["Google Cloud Platform (GCP)"]
        out[category] = _merge_unique_technologies(out[category], gcp_values)[:12]

    return out


def _literal_technology_present(text: str, label: str) -> bool:
    aliases = list(TECH_ALIASES.get(label, ()))
    if not aliases:
        aliases = [label]
    low = (text or "").casefold()
    for alias in aliases:
        alias = str(alias).strip().casefold()
        if alias and re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", low):
            return True
    for cloud_rows in CLOUD_SERVICE_CATALOG.values():
        for cloud_label, pattern in cloud_rows:
            if cloud_label.casefold() == label.casefold() and re.search(pattern, text or "", flags=re.I):
                return True
    return False


def _technology_candidates(skills: dict) -> list[str]:
    master = load_master_resume()
    values = []
    for group in master["skills"].values():
        values.extend(group)
    for group in (skills or {}).values():
        values.extend(group or [])
    for cloud_rows in CLOUD_SERVICE_CATALOG.values():
        values.extend(label for label, _ in cloud_rows)
    return _merge_unique_technologies(values)


def _historical_allowed_technologies(company: str) -> set[str]:
    master = load_master_resume()
    row = next(item for item in master["experience"] if item["company"] == company)
    text = "\n".join(row.get("bullets", [])) + "\n" + str(row.get("environment", ""))
    allowed = {
        label.casefold()
        for label in _technology_candidates(master["skills"])
        if _literal_technology_present(text, label)
    }
    return allowed


def _older_bullet_is_invalid(company: str, bullet: str, normalized_skills: dict) -> bool:
    if OLDER_EMPLOYER_AI_PATTERN.search(bullet or ""):
        return True

    selected = employer_cloud_modes("").get(company)
    detected = detect_cloud_families(bullet or "")
    if selected and (detected - {selected}):
        return True

    allowed = _historical_allowed_technologies(company)
    for label in _technology_candidates(normalized_skills):
        if _literal_technology_present(bullet, label) and label.casefold() not in allowed:
            return True
    return False


def _skills_used_from_bullets(bullets: list[str], normalized_skills: dict) -> list[str]:
    text = "\n".join(bullets)
    found = [
        label
        for label in _technology_candidates(normalized_skills)
        if _literal_technology_present(text, label)
    ]
    # Prefer concrete tools/services; keep the footer short enough to stay visually compact.
    return _merge_unique_technologies(found)[:14]


def _normalize_experience(raw_experience, normalized_skills: dict) -> list[dict]:
    master = load_master_resume()
    source = {
        str(item.get("company") or ""): deepcopy(item)
        for item in (raw_experience or [])
        if isinstance(item, dict)
    }
    out = []
    for master_row in master["experience"]:
        company = master_row["company"]
        item = source.get(company, {"company": company})
        bullets = [str(value).strip() for value in (item.get("bullets") or []) if str(value).strip()]

        if company in OLDER_EMPLOYERS:
            if len(bullets) != len(master_row["bullets"]):
                bullets = list(master_row["bullets"])
            else:
                bullets = [
                    master_row["bullets"][index]
                    if _older_bullet_is_invalid(company, bullet, normalized_skills)
                    else bullet
                    for index, bullet in enumerate(bullets)
                ]

        normalized = {
            "company": company,
            "bullets": bullets,
            "skills_used": _skills_used_from_bullets(bullets, normalized_skills),
        }
        out.append(normalized)
    return out


def _reconcile_skills_with_final_experience(skills: dict, experience: list[dict], description: str) -> dict:
    """Build Technical Skills from the final resume, not from the JD alone.

    Preserve the LLM's JD-adaptive taxonomy, then guarantee that technologies
    credibly evidenced across Fidelity, Cigna, and Target remain represented.
    """
    master = load_master_resume()
    out = {str(k): list(v or []) for k, v in (skills or {}).items() if str(k).strip()}
    final_text = "\n".join(
        "\n".join(item.get("bullets") or [])
        for item in (experience or [])
        if isinstance(item, dict)
    )

    # Historical employer environments are source-of-truth evidence too. This
    # specifically preserves Cigna's Azure and Target's AWS experience even when
    # the current JD selects only one cloud for Fidelity.
    history_text = final_text + "\n" + "\n".join(
        str(row.get("environment") or "")
        for row in master.get("experience") or []
    )

    candidates = _technology_candidates(out)
    evidenced = [
        label for label in candidates
        if _literal_technology_present(history_text, label)
    ]

    # Map evidenced technologies back into an existing adaptive category when
    # possible; otherwise use the corresponding master category.
    master_category_for = {}
    for category, values in (master.get("skills") or {}).items():
        for value in values or []:
            master_category_for[_canonical_technology_label(value).casefold()] = str(category)

    for label in evidenced:
        family = next(iter(detect_cloud_families(label)), None)
        if family in {CLOUD_AWS, CLOUD_AZURE, CLOUD_GCP}:
            category = _find_category(out, family)
        else:
            category = None

        if category is None:
            category = master_category_for.get(label.casefold())

        if category is None:
            # If the LLM already placed the technology in an adaptive category,
            # keep that taxonomy instead of creating a duplicate row.
            category = next(
                (
                    name for name, values in out.items()
                    if any(_canonical_technology_label(v).casefold() == label.casefold() for v in values)
                ),
                "Data Engineering & Processing",
            )

        out.setdefault(category, [])
        out[category] = _merge_unique_technologies(out[category], [label])[:14]

    # Global canonical de-duplication. Cloud technologies must live in their
    # matching cloud category (AWS/Azure/GCP) when such a category exists;
    # otherwise preserve the first adaptive category chosen by the LLM.
    preferred_category = {}
    category_order = list(out)
    for name, values in out.items():
        for value in values:
            canonical = _canonical_technology_label(value)
            key = canonical.casefold()
            families = detect_cloud_families(canonical)
            family = next(iter(families), None)
            if family and _category_matches(name, family):
                preferred_category[key] = name
            elif key not in preferred_category:
                preferred_category[key] = name

    deduped = {name: [] for name in category_order}
    emitted = set()
    for name in category_order:
        for value in out[name]:
            canonical = _canonical_technology_label(value)
            key = canonical.casefold()
            if key in emitted or preferred_category.get(key) != name:
                continue
            emitted.add(key)
            deduped[name].append(canonical)

    return {name: values for name, values in deduped.items() if values}


def _summary_contract_violations(summary) -> list[str]:
    text = str(summary or "").strip()
    reasons = []
    if not text:
        return ["professional summary is empty"]
    if "\n\n" in text:
        reasons.append("professional summary must be one paragraph")
    words = re.findall(r"\b[\w+/#.-]+\b", text)
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
    if len(words) < 95:
        reasons.append(f"professional summary is too short ({len(words)} words; minimum 95)")
    if len(words) > 160:
        reasons.append(f"professional summary is too long ({len(words)} words; maximum 160)")
    if len(sentences) < 4:
        reasons.append(f"professional summary needs at least 4 complete sentences; got {len(sentences)}")
    if text.lstrip().startswith(("-", "•", "*")):
        reasons.append("professional summary must be prose, not a bullet")
    return reasons


def _assert_no_duplicate_technologies(skills: dict, experience: list[dict]) -> None:
    """Hard-stop duplicate canonical technologies in Skills or any Environment footer."""
    seen = set()
    duplicates = []
    for category, values in (skills or {}).items():
        for value in values or []:
            canonical = _canonical_technology_label(value)
            key = canonical.casefold()
            if key in seen:
                duplicates.append(canonical)
            else:
                seen.add(key)
    if duplicates:
        raise RuntimeError(
            "Technical Skills contains duplicate technology entries after canonicalization: "
            + ", ".join(sorted(set(duplicates), key=str.casefold))
        )

    for item in experience or []:
        company = str(item.get("company") or "Unknown employer")
        seen_env = set()
        env_dupes = []
        for value in item.get("skills_used") or []:
            canonical = _canonical_technology_label(value)
            key = canonical.casefold()
            if key in seen_env:
                env_dupes.append(canonical)
            else:
                seen_env.add(key)
        if env_dupes:
            raise RuntimeError(
                f"{company} Environment contains duplicate technology entries after canonicalization: "
                + ", ".join(sorted(set(env_dupes), key=str.casefold))
            )


def _normalize_generated_resume(result: dict, job) -> dict:
    normalized = deepcopy(result)
    description = job.description or ""

    # First establish a provisional technology vocabulary so historical
    # credibility checks can validate the generated employer bullets.
    provisional_skills = _normalize_skills(normalized.get("skills"), description)

    # Finalize all employer bullets before deciding the top Technical Skills.
    normalized["experience"] = _normalize_experience(
        normalized.get("experience"),
        provisional_skills,
    )

    # Now derive/reconcile Technical Skills from the complete final resume.
    normalized["skills"] = _reconcile_skills_with_final_experience(
        provisional_skills,
        normalized["experience"],
        description,
    )
    _assert_no_duplicate_technologies(
        normalized["skills"],
        normalized["experience"],
    )
    return normalized


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
    model = os.getenv("RESUME_LLM_MODEL", "gpt-5.6-sol")
    prompt = build_prompt(job, profile, audit_feedback, coverage_plan)
    cache_key = _cache_key(model, prompt)
    cached = _read_cache(cache_key)
    if cached is not None:
        print(f"Resume LLM cache HIT | {cache_key[:12]} | API call skipped", flush=True)
        return _normalize_generated_resume(cached, job)

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

    summary_issues = _summary_contract_violations(result.get("summary"))
    if summary_issues:
        retry_prompt = deepcopy(prompt)
        retry_prompt["revision_mode"] = True
        retry_prompt["summary_quality_feedback"] = summary_issues
        retry_prompt["task"] = (
            "Regenerate the resume with the same factual and historical constraints. "
            "Fix the Professional Summary specifically: return one substantial 100-140 word prose paragraph "
            "with 4-6 complete sentences and enough senior Data Engineer substance. Do not return summary bullets or fragments."
        )
        retry_body = json.dumps(
            {
                "model": model,
                "instructions": SYSTEM_PROMPT,
                "input": json.dumps(retry_prompt),
                "max_output_tokens": 14000,
            }
        ).encode("utf-8")
        retry_req = request.Request(
            endpoint,
            data=retry_body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(retry_req, timeout=180) as response:
                retry_payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API summary retry HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"OpenAI API summary retry connection error: {exc.reason}") from exc
        retry_text = _extract_output_text(retry_payload)
        try:
            result = json.loads(retry_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenAI returned non-JSON resume output on summary retry: {retry_text[:1200]}") from exc
        if not isinstance(result, dict):
            raise RuntimeError("OpenAI returned a summary-retry payload that is not a JSON object")
        remaining = _summary_contract_violations(result.get("summary"))
        if remaining:
            raise RuntimeError("Generated Professional Summary failed quality contract after retry: " + "; ".join(remaining))

    result = _normalize_generated_resume(result, job)
    _write_cache(cache_key, result)
    return result
