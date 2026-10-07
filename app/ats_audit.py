from __future__ import annotations

import re
from collections import Counter

from docx import Document

from app.cloud_policy import cloud_policy_violations, employer_cloud_modes
from app.jd_coverage_plan import build_coverage_plan
from app.master_resume import load_master_resume
from app.resume_tailoring_policy import determine_tailoring_policy, minimum_skill_rows

from app.master_resume import experience_bullet_counts

ATS_TARGET = 95
HUMAN_QUALITY_TARGET = 90
MIN_EXPERIENCE_DEPTH = 85
EXPECTED_COUNTS = experience_bullet_counts()

METRIC_TOKEN_PATTERNS = [
    r"\b\d+(?:\.\d+)?\s*%",
    r"\b\d+(?:\.\d+)?\s*(?:k|m|b|million|billion)\b",
    r"\b\d+(?:\.\d+)?\s*(?:gb|tb|pb|mb)(?:/day)?\b",
    r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|minutes?|hours?)\b",
    r"\b(?:sub|under|below|less than)\s*[- ]?(?:second|minute|hour)\b",
    r"\b\d+(?:\.\d+)?\+?\s*(?:events?|records?|rows?|transactions?|members?|pipelines?|tables?|datasets?|jobs?|rules?)\b",
]
TECH_NUMBER_PATTERNS = [r"\bs3\b", r"\bec2\b", r"\bscd\s*(?:type\s*)?2\b", r"\bgen\s*2\b", r"\badls\s*gen2\b", r"\bpython\s*3\b"]

TERM_ALIASES = {
    "Apache Kafka": ["Apache Kafka", "Kafka"],
    "Apache Spark": ["Apache Spark", "Spark", "PySpark"],
    "PySpark": ["PySpark"],
    "Airflow": ["Airflow", "Apache Airflow"],
    "Azure Data Factory": ["Azure Data Factory", "Data Factory", "ADF"],
    "Azure Synapse Analytics": ["Azure Synapse Analytics", "Azure Synapse", "Synapse Analytics"],
    "ADLS Gen2": ["ADLS Gen2", "Azure Data Lake Storage Gen2", "ADLS"],
    "Azure Event Hubs": ["Azure Event Hubs", "Azure Event Hub", "Event Hubs", "Event Hub"],
    "Amazon Redshift": ["Amazon Redshift", "Redshift"],
    "AWS Glue": ["AWS Glue", "Glue"],
    "Amazon S3": ["Amazon S3", "S3"],
    "Amazon EMR": ["Amazon EMR", "EMR"],
    "AWS Lambda": ["AWS Lambda", "Lambda"],
    "AWS Kinesis": ["AWS Kinesis", "Amazon Kinesis", "Kinesis"],
    "Snowflake": ["Snowflake"],
    "Databricks": ["Databricks"],
    "BigQuery": ["BigQuery", "Google BigQuery"],
    "Dataflow": ["Dataflow", "Google Cloud Dataflow"],
    "Pub/Sub": ["Pub/Sub", "PubSub", "Google Pub/Sub"],
    "Dataproc": ["Dataproc", "Google Cloud Dataproc"],
    "Cloud Composer": ["Cloud Composer", "Google Cloud Composer"],
    "Kubernetes": ["Kubernetes", "K8s"],
    "Terraform": ["Terraform"],
    "Docker": ["Docker"],
    "dbt": ["dbt"],
    "Data Lineage": ["Data Lineage", "lineage"],
    "Data Quality": ["Data Quality", "data-quality"],
    "Data Governance": ["Data Governance", "governance"],
    "Performance Tuning": ["Performance Tuning", "Performance Optimization", "optimized", "optimizing"],
    "Batch Processing": ["batch processing", "batch pipeline", "batch pipelines", "batch workflow"],
    "Real-Time Data Processing": ["real-time data processing", "real time data processing", "streaming pipeline", "streaming pipelines", "event-driven pipeline"],
    "ETL/ELT": ["ETL", "ELT", "ETL/ELT"],
    "Data Modeling": ["data modeling", "data modelling", "data model", "dimensional modeling", "star schema"],
    "Requirements Gathering": ["requirements gathering", "gathering requirements", "business requirements", "technical requirements"],
    "Solution Design & Development": ["solution design", "solution development", "design and development", "designed and developed"],
    "Solution Implementation & Support": ["implementation and support", "implement and support", "production support", "application support"],
    "Data Integration Solutions": ["data integration solutions", "data integration", "integrations"],
    "Proof of Concepts": ["proof of concept", "proof-of-concept", "POC", "prototype"],
    "Testing & Quality Assurance": ["unit testing", "integration testing", "performance testing", "quality assurance", "testing"],
    "Security & Governance": ["security and governance", "access control", "data governance", "compliance"],
}

DOMAIN_TERMS = {
    "financial": ("trading", "trade data", "market data", "securities", "portfolio", "investment", "risk analytics", "regulatory reporting"),
    "healthcare": ("claims", "eligibility", "member data", "patient", "clinical", "ehr", "hipaa", "provider data"),
    "retail": ("pos", "point of sale", "inventory", "merchandising", "e-commerce", "ecommerce", "orders", "product catalog", "store sales"),
}
EMPLOYER_DOMAIN = {"Fidelity Investments": "financial", "Cigna Healthcare": "healthcare", "Target Corporation": "retail"}

# User historical-timeline rule: AI-era technologies are valid only in the
# current Fidelity role, never in Cigna (2022-2023) or Target (2020-2021).
OLDER_EMPLOYER_AI_PATTERN = re.compile(
    r"(?i)(?:\bartificial intelligence\b|\bAI/ML\b|\bgenerative AI\b|\bgenAI\b|"
    r"\blarge language models?\b|\bLLMs?\b|\bretrieval[- ]augmented generation\b|\bRAG\b|"
    r"\bvector stores?\b|\bvector search\b|\bembeddings?\b|\bMLOps\b|\bmodel serving\b|"
    r"\bmodel inference\b|\bfeature stores?\b|\bClaude\b|\bCursor\b)"
)


def _norm(value):
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def _literal_contains(text, term):
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(_norm(term)) + r"(?![a-z0-9])", _norm(text)))


def _contains(text, term):
    return any(_literal_contains(text, alias) for alias in TERM_ALIASES.get(term, [term]))


def _domain_coherence_violations(by_company):
    findings = []
    for company, bullets in by_company.items():
        expected = EMPLOYER_DOMAIN.get(company)
        for bullet in bullets:
            low = _norm(bullet)
            for domain, terms in DOMAIN_TERMS.items():
                if domain == expected:
                    continue
                hits = [term for term in terms if _literal_contains(low, term)]
                if hits:
                    findings.append(
                        {
                            "company": company,
                            "expected_domain": expected,
                            "conflicting_domain": domain,
                            "terms": hits,
                            "bullet": bullet,
                        }
                    )
    return findings


def _temporal_credibility_violations(by_company):
    findings = []
    for company in ("Cigna Healthcare", "Target Corporation"):
        for bullet in by_company.get(company, []):
            hits = list(dict.fromkeys(match.group(0) for match in OLDER_EMPLOYER_AI_PATTERN.finditer(bullet)))
            if hits:
                findings.append(
                    {
                        "company": company,
                        "reason": "AI-era technology is not permitted in historical pre-current-employer experience",
                        "terms": hits,
                        "bullet": bullet,
                    }
                )
    return findings


def document_text(path):
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def _experience_sections(paragraphs):
    """Read employer bullets from both legacy labeled and current no-label master layouts.

    The live master puts company/location on one line, title/dates on the next,
    then bullets directly before the Environment footer. Older generated files
    can still contain a literal "Roles & Responsibilities:" line, so support both.
    """
    master = load_master_resume()
    titles = {row["company"]: str(row.get("title") or "").strip() for row in master["experience"]}
    by_company = {company: [] for company in EXPECTED_COUNTS}
    footers = {company: "" for company in EXPECTED_COUNTS}
    current = None
    in_roles = False
    for paragraph in paragraphs:
        text = paragraph.text.strip()
        matched_company = next((company for company in EXPECTED_COUNTS if text.startswith(company)), None)
        if matched_company:
            current = matched_company
            in_roles = False
            continue
        if not current:
            continue
        if text.startswith("Environment:") or text.startswith("Skills:"):
            footers[current] = text
            current = None
            in_roles = False
            continue
        if text == "Roles & Responsibilities:":
            in_roles = True
            continue
        if not in_roles:
            title = titles.get(current, "")
            if title and (text == title or text.startswith(title + "\t")):
                in_roles = True
            continue
        if text:
            by_company[current].append(text)
    return by_company, footers


def _experience_bullets(paragraphs):
    by_company, _ = _experience_sections(paragraphs)
    return by_company


def _experience_cloud_text(paragraphs):
    by_company, footers = _experience_sections(paragraphs)
    return {
        company: "\n".join(rows + ([footers[company]] if footers.get(company) else []))
        for company, rows in by_company.items()
    }


def _section_rows(paragraphs, start_heading, end_heading):
    collecting = False
    rows = []
    for paragraph in paragraphs:
        text = paragraph.text.strip()
        if text.upper() == start_heading.upper():
            collecting = True
            continue
        if collecting and text.upper() == end_heading.upper():
            break
        if collecting and text:
            rows.append(text)
    return rows


def _technical_skills_text(paragraphs):
    return "\n".join(_section_rows(paragraphs, "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE"))


def _metric_sanitized(text):
    value = _norm(text)
    for pattern in TECH_NUMBER_PATTERNS:
        value = re.sub(pattern, " ", value, flags=re.I)
    return value


def _metric_tokens(text):
    value = _metric_sanitized(text)
    return list(dict.fromkeys(m.group(0) for pattern in METRIC_TOKEN_PATTERNS for m in re.finditer(pattern, value, flags=re.I)))


def _repetition_findings(bullets):
    normalized = [re.findall(r"[a-z0-9+#.-]+", _norm(x)) for x in bullets]
    phrases = Counter()
    for words in normalized:
        seen = set()
        for size in (4, 5, 6):
            for index in range(max(0, len(words) - size + 1)):
                phrase = " ".join(words[index : index + size])
                if phrase not in seen:
                    phrases[phrase] += 1
                    seen.add(phrase)
    repeated = [phrase for phrase, count in phrases.items() if count >= 3]
    openings = Counter(words[0] for words in normalized if words)
    return repeated[:10], {key: value for key, value in openings.items() if value >= 5}


def _readability_score(bullets, repetition_score):
    if not bullets:
        return 0
    lengths = [len(re.findall(r"\b\w+[+#.-]*\b", bullet)) for bullet in bullets]
    score = 100 - min(25, sum(length > 38 for length in lengths) * 3) - min(20, sum(length > 50 for length in lengths) * 5)
    if sum(lengths) / len(lengths) > 34:
        score -= 10
    return max(40, round(min(score, repetition_score)))


def _required_target_terms(terms):
    return list(dict.fromkeys(terms or []))


def _master_bullet_sets(master):
    return {
        row["company"]: {_norm(bullet) for bullet in row.get("bullets", [])}
        for row in master["experience"]
    }


def _retained_master_counts(by_company, master):
    master_sets = _master_bullet_sets(master)
    return {
        company: sum(_norm(bullet) in master_sets.get(company, set()) for bullet in rows)
        for company, rows in by_company.items()
    }


def _new_metric_findings(by_company, master, zero_target_master):
    if zero_target_master:
        return []
    master_sets = _master_bullet_sets(master)
    findings = []
    for company, rows in by_company.items():
        for bullet in rows:
            metrics = _metric_tokens(bullet)
            if not metrics:
                continue
            if _norm(bullet) in master_sets.get(company, set()):
                continue
            findings.append({"company": company, "metrics": metrics, "bullet": bullet})
    return findings


def ats_audit(job, profile, resume_path):
    text = document_text(resume_path)
    low = _norm(text)
    plan = build_coverage_plan(job, profile)
    policy = determine_tailoring_policy(job, plan)
    master = load_master_resume()

    must_cover_terms = plan.get("must_cover_terms", [])
    preferred_terms = plan.get("preferred_terms", [])
    alternative_terms = plan.get("alternative_terms", [])
    targeted = _required_target_terms(must_cover_terms)
    present = [term for term in targeted if _contains(low, term)]
    missing = [term for term in targeted if not _contains(low, term)]
    keyword_coverage = 100 if not targeted else 100 * len(present) / len(targeted)

    optional_terms = preferred_terms + alternative_terms
    optional_present = [term for term in optional_terms if _contains(low, term)]
    optional_coverage = 100 if not optional_terms else 100 * len(optional_present) / len(optional_terms)

    title_tokens = [x for x in re.findall(r"[a-z]+", _norm(job.title)) if x not in {"senior", "lead", "ii", "iii"}]
    title_alignment = 100 if all(token in low for token in title_tokens) else 70
    sections = {"professional summary", "technical skills", "professional experience", "education"}
    section_score = 100 * sum(section in low for section in sections) / len(sections)

    paragraphs = Document(resume_path).paragraphs
    by_company = _experience_bullets(paragraphs)
    bullets = [bullet for rows in by_company.values() for bullet in rows]
    experience_text = "\n".join(bullets)
    experience_covered = [term for term in must_cover_terms if _contains(experience_text, term)]
    experience_gaps = [term for term in must_cover_terms if not _contains(experience_text, term)]
    experience_coverage = 100 if not must_cover_terms else 100 * len(experience_covered) / len(must_cover_terms)

    counts = {company: len(rows) for company, rows in by_company.items()}
    bullet_count_score = 100 if counts == EXPECTED_COUNTS else 60
    zero_target_master = not must_cover_terms and not plan.get("targeted_terms", [])

    retained_counts = _retained_master_counts(by_company, master)
    retention_floors = policy["minimum_master_bullets_retained"]
    retention_violations = {
        company: {"retained": retained_counts.get(company, 0), "minimum": minimum}
        for company, minimum in retention_floors.items()
        if retained_counts.get(company, 0) < minimum
    }

    metric_findings = _new_metric_findings(by_company, master, zero_target_master)
    metric_counts = {
        company: sum(item["company"] == company for item in metric_findings)
        for company in EXPECTED_COUNTS
    }
    metric_violations = {
        company: {"count": count, "limit": 0}
        for company, count in metric_counts.items()
        if count > 0
    }

    summary_rows = _section_rows(paragraphs, "PROFESSIONAL SUMMARY", "TECHNICAL SKILLS")
    summary_text = " ".join(summary_rows)
    master_summary_text = " ".join(master["summary"])
    summary_density_ratio = len(_norm(summary_text)) / max(1, len(_norm(master_summary_text)))
    summary_min = float(policy["summary_min_master_density_ratio"])
    summary_max = float(policy["summary_max_master_density_ratio"])

    skill_rows = _section_rows(paragraphs, "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE")
    master_skill_rows = len(master["skills"])
    min_skill_rows = minimum_skill_rows(master_skill_rows, policy)
    density_violations = {}
    if not (summary_min <= summary_density_ratio <= summary_max):
        density_violations["summary"] = {
            "ratio": round(summary_density_ratio, 3),
            "minimum": summary_min,
            "maximum": summary_max,
        }
    if len(skill_rows) < min_skill_rows:
        density_violations["technical_skills"] = {
            "rows": len(skill_rows),
            "minimum_rows": min_skill_rows,
            "master_rows": master_skill_rows,
        }

    domain_violations = _domain_coherence_violations(by_company)
    temporal_violations = _temporal_credibility_violations(by_company)
    cloud_modes = employer_cloud_modes(job.description or "")
    cloud_violations = cloud_policy_violations(_experience_cloud_text(paragraphs), job.description or "")
    repeated_phrases, repeated_openings = _repetition_findings(bullets)
    repetition_score = max(
        40,
        100 - min(35, len(repeated_phrases) * 7) - min(20, sum(value - 4 for value in repeated_openings.values()) * 4),
    )
    readability_score = _readability_score(bullets, repetition_score)
    accomplishment_score = 90 if zero_target_master else 88
    human_quality_score = round(readability_score * 0.45 + repetition_score * 0.25 + accomplishment_score * 0.15 + bullet_count_score * 0.15)
    compatibility_score = round(keyword_coverage * 0.60 + title_alignment * 0.15 + section_score * 0.10 + bullet_count_score * 0.10 + 5)
    recruiter_fit_score = round(keyword_coverage * 0.30 + experience_coverage * 0.35 + human_quality_score * 0.20 + title_alignment * 0.10 + section_score * 0.05)
    score = round(compatibility_score * 0.70 + human_quality_score * 0.30)

    jd_specific_bullets = (
        sum(any(_contains(bullet, term) for term in must_cover_terms) for bullet in bullets)
        if must_cover_terms
        else len(bullets)
    )
    minimum_jd_bullets = min(int(policy["minimum_jd_specific_experience_bullets"]), len(bullets))
    experience_gate = (not must_cover_terms) or (
        experience_coverage >= MIN_EXPERIENCE_DEPTH
        and jd_specific_bullets >= minimum_jd_bullets
    )
    discovery_score = getattr(job, "discovery_score", None)
    gates = {
        "discovery": discovery_score is None or discovery_score >= 80,
        "structure": counts == EXPECTED_COUNTS,
        "master_retention": not retention_violations,
        "content_density": not density_violations,
        "metrics": not metric_violations and not metric_findings,
        # Temporal credibility is deliberately folded into the existing blocking
        # domain gate so older-employer AI claims can never become Ready to Apply.
        "domain_coherence": not domain_violations and not temporal_violations,
        "cloud_credibility": not cloud_violations,
        "repetition": repetition_score >= 85,
        "human_quality": human_quality_score >= HUMAN_QUALITY_TARGET,
        "experience_depth": experience_gate,
    }
    quality_gate = all(gates.values())
    passed = score >= ATS_TARGET and keyword_coverage >= 95 and not missing and quality_gate

    return {
        "passed": passed,
        "internal_ats_score": score,
        "target": ATS_TARGET,
        "compatibility_score": compatibility_score,
        "recruiter_fit_score": recruiter_fit_score,
        "human_quality_score": human_quality_score,
        "human_quality_target": HUMAN_QUALITY_TARGET,
        "readability_score": readability_score,
        "keyword_coverage": round(keyword_coverage),
        "title_alignment": round(title_alignment),
        "section_score": round(section_score),
        "accomplishment_score": accomplishment_score,
        "targeted_jd_terms": targeted,
        "preferred_jd_terms": preferred_terms,
        "alternative_jd_terms": alternative_terms,
        "optional_jd_coverage": round(optional_coverage),
        "optional_jd_terms_present": optional_present,
        "missing_jd_keywords": missing,
        "must_cover_experience_terms": must_cover_terms,
        "experience_covered_terms": experience_covered,
        "experience_depth_gaps": experience_gaps,
        "experience_depth_coverage": round(experience_coverage),
        "jd_specific_experience_bullets": jd_specific_bullets,
        "minimum_jd_specific_experience_bullets": minimum_jd_bullets,
        "tailoring_policy": policy,
        "master_bullets_retained_by_employer": retained_counts,
        "master_retention_violations": retention_violations,
        "summary_density_ratio": round(summary_density_ratio, 3),
        "technical_skill_rows": len(skill_rows),
        "minimum_technical_skill_rows": min_skill_rows,
        "content_density_violations": density_violations,
        "metric_bearing_new_or_rewritten_bullets": sum(metric_counts.values()),
        "metric_counts_by_employer": metric_counts,
        "metric_violations": metric_violations,
        "unapproved_metric_claims": metric_findings,
        "domain_coherence_violations": domain_violations,
        "temporal_credibility_violations": temporal_violations,
        "employer_cloud_modes": cloud_modes,
        "cloud_policy_violations": cloud_violations,
        "approved_metric_patterns": {"verbatim_master_bullets": "user-authoritative existing metrics only"},
        "bullet_counts": counts,
        "bullet_count_score": bullet_count_score,
        "skills_taxonomy_score": 100,
        "repetition_score": repetition_score,
        "repeated_phrases": repeated_phrases,
        "repeated_opening_verbs": repeated_openings,
        "discovery_score": discovery_score,
        "quality_gate_passed": quality_gate,
        "quality_gates": gates,
        "status": "ATS_PASS" if passed else "HOLD_ATS_REVIEW",
        "note": "Internal ATS/recruiter-fit estimates only; not a proprietary employer ATS score.",
    }
