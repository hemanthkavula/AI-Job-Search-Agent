from __future__ import annotations

import re

CLOUD_AWS = "AWS"
CLOUD_AZURE = "AZURE"
CLOUD_GCP = "GCP"

# Deliberately use provider/service names that are strong cloud signals. Generic
# cross-cloud technologies such as Databricks, Spark, Kafka, Airflow, Snowflake,
# Kubernetes, and Terraform do not select a cloud family by themselves.
CLOUD_PATTERNS = {
    CLOUD_AWS: (
        r"\baws\b",
        r"amazon web services",
        r"\bamazon s3\b|\bs3\b",
        r"\baws glue\b",
        r"\bamazon emr\b|\bemr\b",
        r"\bamazon redshift\b|\bredshift\b",
        r"\baws lambda\b",
        r"\bamazon kinesis\b|\bkinesis\b",
        r"\baws step functions?\b",
        r"\bathena\b",
    ),
    CLOUD_AZURE: (
        r"\bazure\b",
        r"microsoft azure",
        r"azure data factory",
        r"\badf\b",
        r"\badls(?:\s*gen\s*2)?\b",
        r"azure data lake storage",
        r"azure synapse|synapse analytics",
        r"event hubs?",
        r"azure functions?",
        r"azure purview|microsoft purview",
    ),
    CLOUD_GCP: (
        r"\bgcp\b",
        r"google cloud(?: platform)?",
        r"\bbigquery\b",
        r"\bdataflow\b",
        r"\bpub\s*/?\s*sub\b|\bpubsub\b",
        r"google cloud storage|\bgcs\b",
        r"\bdataproc\b",
        r"cloud composer",
        r"google cloud functions?",
        r"cloud run",
    ),
}


def detect_cloud_families(text: str) -> set[str]:
    value = text or ""
    return {
        cloud
        for cloud, patterns in CLOUD_PATTERNS.items()
        if any(re.search(pattern, value, flags=re.I) for pattern in patterns)
    }


def fidelity_cloud_mode(job_description: str) -> str:
    """Return the single cloud family Fidelity is allowed to use.

    User credibility rule:
    - exactly one cloud family in the JD -> use that cloud only;
    - multi-cloud JD (2+ families) -> use AWS only;
    - cloud-neutral JD -> default to the master-backed AWS history.
    """
    families = detect_cloud_families(job_description)
    if len(families) == 1:
        return next(iter(families))
    return CLOUD_AWS


def employer_cloud_modes(job_description: str) -> dict[str, str]:
    return {
        "Fidelity Investments": fidelity_cloud_mode(job_description),
        "Cigna Healthcare": CLOUD_AZURE,
        "Target Corporation": CLOUD_AWS,
    }


def forbidden_cloud_families(company: str, job_description: str) -> set[str]:
    selected = employer_cloud_modes(job_description).get(company)
    if not selected:
        return set()
    return {CLOUD_AWS, CLOUD_AZURE, CLOUD_GCP} - {selected}


def cloud_policy_violations(company_text: dict[str, str], job_description: str) -> list[dict]:
    findings = []
    selected_modes = employer_cloud_modes(job_description)
    for company, text in company_text.items():
        if company not in selected_modes:
            continue
        detected = detect_cloud_families(text)
        forbidden = detected - {selected_modes[company]}
        if forbidden:
            findings.append(
                {
                    "company": company,
                    "selected_cloud": selected_modes[company],
                    "forbidden_clouds": sorted(forbidden),
                }
            )
    return findings
