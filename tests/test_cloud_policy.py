from types import SimpleNamespace

from app.cloud_policy import (
    CLOUD_AWS,
    CLOUD_AZURE,
    CLOUD_GCP,
    cloud_policy_violations,
    employer_cloud_modes,
    fidelity_cloud_mode,
)
from app.llm_resume_writer import build_prompt


def test_fidelity_uses_single_azure_cloud_when_jd_is_azure_only():
    jd = "Build Azure Data Factory and ADLS Gen2 pipelines with Azure Synapse."
    assert fidelity_cloud_mode(jd) == CLOUD_AZURE


def test_fidelity_uses_single_gcp_cloud_when_jd_is_gcp_only():
    jd = "Build Google Cloud pipelines using BigQuery, Dataflow, and Pub/Sub."
    assert fidelity_cloud_mode(jd) == CLOUD_GCP


def test_fidelity_uses_single_aws_cloud_when_jd_is_aws_only():
    jd = "Build AWS data pipelines using S3, Glue, EMR, and Redshift."
    assert fidelity_cloud_mode(jd) == CLOUD_AWS


def test_fidelity_multicloud_aws_and_azure_resolves_to_aws_only():
    jd = "Multi-cloud platform using AWS S3 and Azure Data Factory."
    assert fidelity_cloud_mode(jd) == CLOUD_AWS


def test_fidelity_multicloud_azure_and_gcp_still_resolves_to_aws_only():
    jd = "Multi-cloud platform using Azure Synapse and Google BigQuery."
    assert fidelity_cloud_mode(jd) == CLOUD_AWS


def test_fidelity_cloud_neutral_jd_defaults_to_master_backed_aws():
    jd = "Build Python SQL and Airflow data pipelines with Spark and Kafka."
    assert fidelity_cloud_mode(jd) == CLOUD_AWS


def test_fixed_employer_cloud_modes_are_preserved():
    modes = employer_cloud_modes("Azure Data Factory and BigQuery multi-cloud platform")
    assert modes == {
        "Fidelity Investments": CLOUD_AWS,
        "Cigna Healthcare": CLOUD_AZURE,
        "Target Corporation": CLOUD_AWS,
    }


def test_cloud_audit_rejects_mixed_fidelity_clouds_for_multicloud_jd():
    jd = "AWS S3 and Azure Data Factory are used across a multi-cloud platform."
    findings = cloud_policy_violations(
        {
            "Fidelity Investments": "Built AWS Glue pipelines and Azure Data Factory workflows.",
            "Cigna Healthcare": "Built Azure Databricks pipelines.",
            "Target Corporation": "Built Amazon S3 pipelines.",
        },
        jd,
    )
    fidelity = next(item for item in findings if item["company"] == "Fidelity Investments")
    assert fidelity["selected_cloud"] == CLOUD_AWS
    assert fidelity["forbidden_clouds"] == [CLOUD_AZURE]


def test_cloud_audit_accepts_aws_only_fidelity_for_multicloud_jd():
    jd = "AWS S3, Azure Data Factory, and BigQuery support a multi-cloud estate."
    findings = cloud_policy_violations(
        {
            "Fidelity Investments": "Built AWS Glue, S3, and Redshift data pipelines.",
            "Cigna Healthcare": "Built Azure Data Factory and ADLS pipelines.",
            "Target Corporation": "Built AWS S3 pipelines.",
        },
        jd,
    )
    assert findings == []


def test_cloud_audit_rejects_aws_or_gcp_inside_cigna_and_azure_or_gcp_inside_target():
    jd = "Experience across AWS, Azure, and GCP is preferred."
    findings = cloud_policy_violations(
        {
            "Fidelity Investments": "Built AWS data pipelines.",
            "Cigna Healthcare": "Built AWS Glue pipelines for claims data.",
            "Target Corporation": "Built Azure Data Factory pipelines for retail data.",
        },
        jd,
    )
    by_company = {item["company"]: item for item in findings}
    assert by_company["Cigna Healthcare"]["selected_cloud"] == CLOUD_AZURE
    assert CLOUD_AWS in by_company["Cigna Healthcare"]["forbidden_clouds"]
    assert by_company["Target Corporation"]["selected_cloud"] == CLOUD_AWS
    assert CLOUD_AZURE in by_company["Target Corporation"]["forbidden_clouds"]


def test_resume_prompt_receives_deterministic_cloud_modes():
    job = SimpleNamespace(
        company="Example",
        title="Senior Data Engineer",
        description="Multi-cloud role using Azure Synapse and Google BigQuery.",
    )
    prompt = build_prompt(job, coverage_plan={"target_count": 4})
    modes = prompt["employer_cloud_credibility_policy"]["selected_cloud_by_employer"]
    assert modes["Fidelity Investments"] == CLOUD_AWS
    assert modes["Cigna Healthcare"] == CLOUD_AZURE
    assert modes["Target Corporation"] == CLOUD_AWS
