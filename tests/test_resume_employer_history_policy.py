from types import SimpleNamespace

from app.llm_resume_writer import _normalize_generated_resume
from app.master_resume import load_master_resume


def _payload():
    return {
        "summary": "Senior Data Engineer.\n\nBuilds reliable data platforms.",
        "skills": {
            "Programming Languages": ["Python", "SQL"],
            "Cloud Platforms": ["GCP", "BigQuery", "Dataflow", "Pub/Sub"],
            "Data Processing": ["Apache Spark", "PySpark", "Databricks"],
        },
        "experience": [
            {
                "company": "Fidelity Investments",
                "bullets": [
                    "Built GCP data pipelines with BigQuery and Dataflow for governed financial analytics.",
                    "Developed Pub/Sub streaming workflows for market-data processing.",
                    "Built Python and SQL transformations for investment data products.",
                    "Designed BigQuery models for portfolio analytics.",
                    "Implemented data quality controls for financial datasets.",
                    "Developed PySpark processing for large financial datasets.",
                    "Built Databricks workflows for controlled data transformations.",
                    "Optimized SQL processing for analytical workloads.",
                    "Automated pipeline delivery using CI/CD practices.",
                    "Partnered with risk and investment stakeholders on data design.",
                ],
                "skills_used": ["GCP", "BigQuery", "Dataflow", "Pub/Sub", "Python", "SQL"],
            },
            {
                "company": "Cigna Healthcare",
                "bullets": [
                    "Built Generative AI and RAG pipelines with vector stores for healthcare claims.",
                    "Built PySpark ETL pipelines on Databricks for healthcare data.",
                    "Designed ADLS Gen2 data lake patterns for healthcare datasets.",
                    "Modeled Snowflake data warehouse structures for claims analytics.",
                    "Built Event Hub streaming workflows for operational events.",
                    "Optimized Spark workloads for healthcare datasets.",
                    "Supported Azure Purview governance and HIPAA data handling.",
                    "Developed Power BI reporting for clinical operations.",
                ],
                "skills_used": ["Generative AI", "RAG", "Databricks"],
            },
            {
                "company": "Target Corporation",
                "bullets": [
                    "Developed BigQuery and Dataflow pipelines for retail sales data.",
                    "Built PySpark pipelines for product and order datasets.",
                    "Designed Redshift warehouse models for retail analytics.",
                    "Built Kafka ingestion for near real-time POS data.",
                    "Implemented Python and SQL validation for retail datasets.",
                    "Optimized PostgreSQL and MySQL reporting workloads.",
                    "Developed Tableau reporting for merchandising teams.",
                    "Supported data-driven retail operations and inventory analysis.",
                ],
                "skills_used": ["BigQuery", "Dataflow", "PySpark"],
            },
        ],
    }


def test_gcp_jd_adds_separate_gcp_group_and_keeps_master_aws_azure_groups():
    job = SimpleNamespace(
        description="GCP BigQuery Dataflow Pub/Sub pipelines using Python SQL and PySpark"
    )
    result = _normalize_generated_resume(_payload(), job)
    master = load_master_resume()

    assert result["skills"]["Cloud Platforms (AWS)"][:6] == master["skills"]["Cloud Platforms (AWS)"]
    assert result["skills"]["Cloud Platforms (Azure)"][:4] == master["skills"]["Cloud Platforms (Azure)"]
    assert "Cloud Platforms (GCP)" in result["skills"]
    assert "BigQuery" in result["skills"]["Cloud Platforms (GCP)"]
    assert "Dataflow" in result["skills"]["Cloud Platforms (GCP)"]
    assert "Pub/Sub" in result["skills"]["Cloud Platforms (GCP)"]


def test_old_employers_reject_ai_and_wrong_cloud_while_fidelity_stays_jd_adaptive():
    job = SimpleNamespace(
        description="GCP BigQuery Dataflow Pub/Sub pipelines using Python SQL and PySpark"
    )
    result = _normalize_generated_resume(_payload(), job)
    master = load_master_resume()
    rows = {item["company"]: item for item in result["experience"]}

    # Fidelity is allowed to use the current JD's GCP stack.
    assert "BigQuery" in " ".join(rows["Fidelity Investments"]["bullets"])
    assert "Dataflow" in " ".join(rows["Fidelity Investments"]["bullets"])

    # Cigna's AI-era bullet is replaced with the same-position master historical bullet.
    assert rows["Cigna Healthcare"]["bullets"][0] == master["experience"][1]["bullets"][0]
    cigna_text = " ".join(rows["Cigna Healthcare"]["bullets"]).lower()
    assert "generative ai" not in cigna_text
    assert "vector store" not in cigna_text
    assert "rag" not in cigna_text

    # Target's GCP bullet is replaced with the same-position AWS-backed master bullet.
    assert rows["Target Corporation"]["bullets"][0] == master["experience"][2]["bullets"][0]
    target_text = " ".join(rows["Target Corporation"]["bullets"]).lower()
    assert "bigquery" not in target_text
    assert "dataflow" not in target_text

    # Employer footer values are derived only from final bullet technology mentions.
    assert all("Generative AI" != value for value in rows["Cigna Healthcare"]["skills_used"])
    assert all("BigQuery" != value for value in rows["Target Corporation"]["skills_used"])


def test_technology_aliases_are_canonicalized_in_skills_and_environment():
    payload = _payload()
    payload["skills"]["Cloud Platforms"] = [
        "Lambda", "AWS Lambda", "Kinesis", "Amazon Kinesis",
        "Data Factory", "Azure Data Factory", "Synapse Analytics", "Azure Synapse Analytics",
        "Azure Data Lake Storage Gen2", "ADLS Gen2", "Event Hub", "Azure Event Hubs",
        "Azure Purview", "Microsoft Purview",
    ]
    payload["experience"][1]["bullets"][1] = (
        "Built PySpark ETL pipelines with Azure Data Factory, Azure Synapse Analytics, "
        "ADLS Gen2, Azure Event Hubs, and Microsoft Purview for healthcare data."
    )
    job = SimpleNamespace(description="Azure data engineering using Data Factory and Synapse")
    result = _normalize_generated_resume(payload, job)

    all_skills = [value for values in result["skills"].values() for value in values]
    assert "Lambda" not in all_skills
    assert "Kinesis" not in all_skills
    assert "Data Factory" not in all_skills
    assert "Synapse Analytics" not in all_skills
    assert "Azure Data Lake Storage Gen2" not in all_skills
    assert "Event Hub" not in all_skills
    assert "Azure Purview" not in all_skills

    cigna = next(item for item in result["experience"] if item["company"] == "Cigna Healthcare")
    footer = cigna["skills_used"]
    assert footer.count("Azure Data Factory") <= 1
    assert footer.count("Azure Synapse Analytics") <= 1
    assert footer.count("ADLS Gen2") <= 1
    assert footer.count("Azure Event Hubs") <= 1
    assert footer.count("Microsoft Purview") <= 1
