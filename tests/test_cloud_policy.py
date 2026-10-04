from types import SimpleNamespace

from app.cloud_policy import (
    CLOUD_AWS,
    CLOUD_AZURE,
    CLOUD_GCP,
    cloud_policy_violations,
    cloud_signal_counts,
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
    jd = "Build AWS data pipelines using S3, AWS Glue, EMR, and Redshift."
    assert fidelity_cloud_mode(jd) == CLOUD_AWS


def test_fidelity_multicloud_chooses_azure_when_azure_is_more_heavily_mentioned():
    jd = "AWS exposure is useful. Primary platform is Azure with Azure Data Factory, ADLS Gen2, Azure Synapse, and Azure Functions."
    counts = cloud_signal_counts(jd)
    assert counts[CLOUD_AZURE] > counts[CLOUD_AWS]
    assert fidelity_cloud_mode(jd) == CLOUD_AZURE


def test_fidelity_multicloud_chooses_gcp_when_gcp_is_more_heavily_mentioned():
    jd = "Some Azure familiarity is helpful. Core platform is GCP with Google Cloud, BigQuery, Dataflow, Pub/Sub, and Dataproc."
    counts = cloud_signal_counts(jd)
    assert counts[CLOUD_GCP] > counts[CLOUD_AZURE]
    assert fidelity_cloud_mode(jd) == CLOUD_GCP


def test_fidelity_multicloud_chooses_aws_when_aws_is_more_heavily_mentioned():
    jd = "Azure knowledge is a plus. Main workloads run on AWS with S3, AWS Glue, EMR, Redshift, Lambda, and Kinesis."
    counts = cloud_signal_counts(jd)
    assert counts[CLOUD_AWS] > counts[CLOUD_AZURE]
    assert fidelity_cloud_mode(jd) == CLOUD_AWS


def test_fidelity_aws_wins_exact_tie_for_master_credibility():
    jd = "AWS S3 and Azure Data Factory are used across the platform."
    counts = cloud_signal_counts(jd)
    assert counts[CLOUD_AWS] == counts[CLOUD_AZURE]
    assert fidelity_cloud_mode(jd) == CLOUD_AWS


def test_fidelity_azure_gcp_tie_uses_first_mentioned_cloud_in_jd():
    jd = "Azure and GCP are both required."
    counts = cloud_signal_counts(jd)
    assert counts[CLOUD_AZURE] == counts[CLOUD_GCP]
    assert fidelity_cloud_mode(jd) == CLOUD_AZURE


def test_fidelity_cloud_neutral_jd_defaults_to_master_backed_aws():
    jd = "Build Python SQL and Airflow data pipelines with Spark and Kafka."
    assert fidelity_cloud_mode(jd) == CLOUD_AWS


def test_fixed_cigna_and_target_cloud_modes_are_preserved_while_fidelity_tracks_dominant_jd_cloud():
    jd = "Azure is primary: Azure Data Factory, ADLS Gen2, Azure Synapse, Azure Functions. Some BigQuery exposure is useful."
    modes = employer_cloud_modes(jd)
    assert modes == {
        "Fidelity Investments": CLOUD_AZURE,
        "Cigna Healthcare": CLOUD_AZURE,
        "Target Corporation": CLOUD_AWS,
    }


def test_cloud_audit_rejects_non_selected_cloud_inside_fidelity():
    jd = "Primary Azure platform with Azure Data Factory, ADLS Gen2, Azure Synapse and Azure Functions. AWS familiarity is a plus."
    findings = cloud_policy_violations(
        {
            "Fidelity Investments": "Built Azure Data Factory pipelines and AWS Glue workflows.",
            "Cigna Healthcare": "Built Azure Databricks pipelines.",
            "Target Corporation": "Built Amazon S3 pipelines.",
        },
        jd,
    )
    fidelity = next(item for item in findings if item["company"] == "Fidelity Investments")
    assert fidelity["selected_cloud"] == CLOUD_AZURE
    assert fidelity["forbidden_clouds"] == [CLOUD_AWS]


def test_cloud_audit_accepts_only_dominant_cloud_in_fidelity():
    jd = "AWS exposure is useful. Primary platform is Azure with Azure Data Factory, ADLS Gen2, Azure Synapse, and Azure Functions."
    findings = cloud_policy_violations(
        {
            "Fidelity Investments": "Built Azure Data Factory, ADLS Gen2, and Azure Synapse data pipelines.",
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


def test_resume_prompt_receives_dominant_cloud_counts_and_modes():
    job = SimpleNamespace(
        company="Example",
        title="Senior Data Engineer",
        description="AWS familiarity is helpful. Azure is primary with Azure Data Factory, ADLS Gen2, Azure Synapse, and Azure Functions.",
    )
    prompt = build_prompt(job, coverage_plan={"target_count": 4})
    policy = prompt["employer_cloud_credibility_policy"]
    modes = policy["selected_cloud_by_employer"]
    counts = policy["jd_cloud_signal_counts"]
    assert counts[CLOUD_AZURE] > counts[CLOUD_AWS]
    assert modes["Fidelity Investments"] == CLOUD_AZURE
    assert modes["Cigna Healthcare"] == CLOUD_AZURE
    assert modes["Target Corporation"] == CLOUD_AWS
