from __future__ import annotations

import re

CLOUD_AWS = "AWS"
CLOUD_AZURE = "AZURE"
CLOUD_GCP = "GCP"

# Strong provider/service signals. Generic cross-cloud technologies such as
# Databricks, Spark, Kafka, Airflow, Snowflake, Kubernetes, Terraform, Python,
# and SQL never select a cloud family by themselves.
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


def cloud_signal_counts(text: str) -> dict[str, int]:
    """Count material cloud-provider/service signals in the JD.

    Counts intentionally include both provider mentions and named services. This
    lets a JD that repeatedly emphasizes one ecosystem outrank a token mention of
    another cloud, which matches the user's 'use whichever is highly mentioned'
    requirement.
    """
    value = text or ""
    return {
        cloud: sum(len(list(re.finditer(pattern, value, flags=re.I))) for pattern in patterns)
        for cloud, patterns in CLOUD_PATTERNS.items()
    }


def detect_cloud_families(text: str) -> set[str]:
    counts = cloud_signal_counts(text)
    return {cloud for cloud, count in counts.items() if count > 0}


def _first_cloud_position(text: str, cloud: str) -> int:
    positions = []
    for pattern in CLOUD_PATTERNS[cloud]:
        match = re.search(pattern, text or "", flags=re.I)
        if match:
            positions.append(match.start())
    return min(positions) if positions else 10**9


def fidelity_cloud_mode(job_description: str) -> str:
    """Return the single cloud family Fidelity is allowed to use.

    Fidelity credibility rule:
    - use the cloud family with the strongest/highest JD signal count;
    - never mix cloud families inside Fidelity experience;
    - if AWS is tied for strongest, use AWS as the master-backed tie-breaker;
    - if only Azure/GCP are tied, use whichever tied cloud appears first in the JD;
    - if the JD has no cloud signal, default to the master-backed AWS history.
    """
    counts = cloud_signal_counts(job_description)
    highest = max(counts.values(), default=0)
    if highest <= 0:
        return CLOUD_AWS

    leaders = [cloud for cloud, count in counts.items() if count == highest]
    if len(leaders) == 1:
        return leaders[0]
    if CLOUD_AWS in leaders:
        return CLOUD_AWS
    return min(leaders, key=lambda cloud: _first_cloud_position(job_description, cloud))


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
