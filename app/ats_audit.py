from __future__ import annotations

import re
from collections import Counter

from docx import Document

from app.jd_coverage_plan import build_coverage_plan

ATS_TARGET = 95
HUMAN_QUALITY_TARGET = 90
MIN_EXPERIENCE_DEPTH = 85
MIN_JD_SPECIFIC_BULLETS = 6
EXPECTED_COUNTS = {"Fidelity Investments": 10, "Cigna Healthcare": 8, "Target Corporation": 8}

# Tailored resumes must not invent quantitative accomplishments. The zero-target
# path uses the unchanged user-authoritative master, so its existing metrics are
# treated as fixed master content rather than newly generated claims.
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
    "Amazon Redshift": ["Amazon Redshift", "Redshift"],
    "AWS Glue": ["AWS Glue", "Glue"],
    "Amazon S3": ["Amazon S3", "S3"],
    "Amazon EMR": ["Amazon EMR", "EMR"],
    "AWS Lambda": ["AWS Lambda", "Lambda"],
    "AWS Kinesis": ["AWS Kinesis", "Amazon Kinesis", "Kinesis"],
    "Snowflake": ["Snowflake"],
    "Databricks": ["Databricks"],
    "BigQuery": ["BigQuery", "Google BigQuery"],
    "Dagster": ["Dagster"],
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
OPTIONAL_LANGUAGE_ALTERNATIVES = {"Go", "Rust", "Scala", "Java"}


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


def document_text(path):
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def _experience_bullets(paragraphs):
    by_company = {company: [] for company in EXPECTED_COUNTS}
    current = None
    for paragraph in paragraphs:
        text = paragraph.text.strip()
        for company in EXPECTED_COUNTS:
            if text.startswith(company):
                current = company
                break
        else:
            if current and paragraph.style and "List Bullet" in paragraph.style.name:
                by_company[current].append(text)
    return by_company


def _technical_skills_text(paragraphs):
    collecting = False
    rows = []
    for paragraph in paragraphs:
        text = paragraph.text.strip()
        if text.upper() == "TECHNICAL SKILLS":
            collecting = True
            continue
        if collecting and text.upper() == "PROFESSIONAL EXPERIENCE":
            break
        if collecting and text:
            rows.append(text)
    return "\n".join(rows)


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


def _required_target_terms(terms, text):
    deduped = []
    for term in terms:
        if term not in deduped:
            deduped.append(term)
    python_present = _contains(text, "Python")
    return [term for term in deduped if not (python_present and term in OPTIONAL_LANGUAGE_ALTERNATIVES)]


def ats_audit(job, profile, resume_path):
    text = document_text(resume_path)
    low = _norm(text)
    plan = build_coverage_plan(job, profile)
    must_cover_terms = plan.get("must_cover_terms", [])
    preferred_terms = plan.get("preferred_terms", [])
    alternative_terms = plan.get("alternative_terms", [])
    targeted = _required_target_terms(must_cover_terms, low)
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
    metric_findings = [] if zero_target_master else [
        {"company": company, "metrics": _metric_tokens(bullet), "bullet": bullet}
        for company, rows in by_company.items()
        for bullet in rows
        if _metric_tokens(bullet)
    ]
    metric_counts = {
        company: 0 if zero_target_master else sum(bool(_metric_tokens(bullet)) for bullet in rows)
        for company, rows in by_company.items()
    }
    metric_violations = {} if zero_target_master else {
        company: {"count": count, "limit": 0}
        for company, count in metric_counts.items()
        if count > 0
    }

    domain_violations = _domain_coherence_violations(by_company)
    repeated_phrases, repeated_openings = _repetition_findings(bullets)
    repetition_score = max(
        40,
        100 - min(35, len(repeated_phrases) * 7) - min(20, sum(value - 4 for value in repeated_openings.values()) * 4),
    )
    readability_score = _readability_score(bullets, repetition_score)
    accomplishment_score = 90 if zero_target_master else 85
    human_quality_score = round(readability_score * 0.45 + repetition_score * 0.25 + accomplishment_score * 0.15 + bullet_count_score * 0.15)
    compatibility_score = round(keyword_coverage * 0.60 + title_alignment * 0.15 + section_score * 0.10 + bullet_count_score * 0.10 + 5)
    recruiter_fit_score = round(keyword_coverage * 0.30 + experience_coverage * 0.35 + human_quality_score * 0.20 + title_alignment * 0.10 + section_score * 0.05)
    score = round(compatibility_score * 0.70 + human_quality_score * 0.30)

    jd_specific_bullets = (
        sum(any(_contains(bullet, term) for term in must_cover_terms) for bullet in bullets)
        if must_cover_terms
        else len(bullets)
    )
    experience_gate = (not must_cover_terms) or (
        experience_coverage >= MIN_EXPERIENCE_DEPTH
        and jd_specific_bullets >= min(MIN_JD_SPECIFIC_BULLETS, len(bullets))
    )
    discovery_score = getattr(job, "discovery_score", None)
    gates = {
        "discovery": discovery_score is None or discovery_score >= 80,
        "structure": counts == EXPECTED_COUNTS,
        "metrics": not metric_violations and not metric_findings,
        "domain_coherence": not domain_violations,
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
        "minimum_jd_specific_experience_bullets": min(MIN_JD_SPECIFIC_BULLETS, len(bullets)),
        "metric_bearing_bullets": sum(metric_counts.values()),
        "metric_counts_by_employer": metric_counts,
        "metric_violations": metric_violations,
        "unapproved_metric_claims": metric_findings,
        "domain_coherence_violations": domain_violations,
        "approved_metric_patterns": {},
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
