import json
from types import SimpleNamespace

from docx import Document

import app.reference_resume_formatter as formatter
from app.llm_resume_writer import build_prompt
from app.master_resume import fixed_personal_facts, master_resume_payload


EXPECTED_WORD_SHA256 = "7bad8e220373e668002750e38e309ce9b695a2caca8cf61297348bafdccb916f"


def test_uploaded_word_is_authoritative_format_record():
    record = formatter.load_word_format()
    assert record["source"]["authority"] == "user_uploaded_word_format_template"
    assert record["source"]["technical_content_authority"] is False
    assert record["source"]["sha256"] == EXPECTED_WORD_SHA256
    assert record["source"]["pages"] == 2
    assert record["style"]["font"] == "Calibri"
    assert record["style"]["body_pt"] == 10.0
    assert record["style"]["top_margin_in"] == 0.50
    assert record["style"]["bottom_margin_in"] == 0.50
    assert record["style"]["left_margin_in"] == 0.50
    assert record["style"]["right_margin_in"] == 0.50
    assert record["style"]["natural_pagination"] is True
    assert record["style"]["forced_page_breaks"] is False


def test_fixed_personal_facts_exclude_master_technical_content():
    facts = fixed_personal_facts()
    serialized = json.dumps(facts).lower()
    for forbidden in (
        "pyspark",
        "snowflake",
        "databricks",
        "kafka",
        "terraform",
        "great expectations",
        "environment",
        "bullets",
    ):
        assert forbidden not in serialized
    assert facts["name"] == "Hemanth Kavula"
    assert [x["company"] for x in facts["employment_history"]] == [
        "Fidelity Investments",
        "Cigna Healthcare",
        "Target Corporation",
    ]


def test_tailoring_prompt_uses_master_historical_baseline_and_fidelity_jd():
    job = SimpleNamespace(
        company="Example",
        title="Data Engineer",
        description=(
            "Build Python and SQL pipelines on GCP with BigQuery, Dataflow, Pub/Sub and Airflow. "
            "Required hands-on Python, SQL, GCP, BigQuery and Dataflow."
        ),
        description_complete=True,
        description_usable=True,
        tailoring_mode="FULL_JD",
    )
    profile_only = {
        "skills": ["PROFILE_ONLY_TOOL"],
        "summary_source": ["PROFILE ONLY SUMMARY"],
        "experience": [{"evidence": ["PROFILE ONLY BULLET"]}],
    }
    prompt = build_prompt(
        job,
        profile_only,
        coverage_plan={
            "target_count": 5,
            "must_cover_terms": ["Python", "SQL", "GCP", "BigQuery", "Dataflow"],
            "targeted_terms": ["Python", "SQL", "GCP", "BigQuery", "Dataflow"],
            "requirements": [
                {"term": "Python", "classification": "required"},
                {"term": "SQL", "classification": "required"},
                {"term": "GCP", "classification": "required"},
                {"term": "BigQuery", "classification": "required"},
                {"term": "Dataflow", "classification": "required"},
            ],
        },
    )
    serialized = json.dumps(prompt)
    assert "PROFILE_ONLY_TOOL" not in serialized
    assert "PROFILE ONLY SUMMARY" not in serialized
    assert "PROFILE ONLY BULLET" not in serialized

    baseline = prompt["master_resume_technical_baseline"]
    assert baseline["skills"]["Cloud Platforms (AWS)"]
    assert baseline["skills"]["Cloud Platforms (Azure)"]
    assert prompt["employer_cloud_credibility_policy"]["selected_cloud_by_employer"]["Fidelity Investments"] == "GCP"
    assert prompt["employer_cloud_credibility_policy"]["selected_cloud_by_employer"]["Cigna Healthcare"] == "AZURE"
    assert prompt["employer_cloud_credibility_policy"]["selected_cloud_by_employer"]["Target Corporation"] == "AWS"
    assert prompt["historical_timeline_policy"]["forbid_ai_era_technology_in_cigna_and_target"] is True
    assert prompt["skills_policy"]["retain_master_aws_group"] is True
    assert prompt["skills_policy"]["retain_master_azure_group"] is True
    assert prompt["skills_policy"]["add_gcp_group_when_fidelity_selects_gcp"] is True
    assert prompt["structure_contract"]["employer_footer_label"] == "Skills"
    assert prompt["structure_contract"]["environment_paragraphs"] is False


def test_master_payload_remains_conservative_fallback():
    payload = master_resume_payload()
    assert payload["_master_mode"] is True
    assert len(payload["experience"][0]["bullets"]) == 10
    assert len(payload["experience"][1]["bullets"]) == 8
    assert len(payload["experience"][2]["bullets"]) == 8
    assert "dbt transformation models" in payload["experience"][0]["bullets"][4]
    assert "AI/ML-driven analytics" in payload["experience"][0]["bullets"][6]


def test_renderer_reproduces_uploaded_word_format_contract_with_skills_footer(monkeypatch, tmp_path):
    monkeypatch.setattr(formatter, "ROOT", tmp_path)
    monkeypatch.setattr(formatter, "WORD_FORMAT_PATH", formatter.WORD_FORMAT_PATH)
    job = SimpleNamespace(company="Example Company", title="Data Engineer")
    path = formatter.render_llm_resume(
        job, {}, master_resume_payload(), output_dir="resumes"
    )
    result = formatter.validate_master_format_contract(path)
    assert result["passed"], result["reasons"]
    doc = Document(path)
    assert doc.paragraphs[0].text == "Hemanth Kavula"
    assert doc.paragraphs[1].text == "Senior Data Engineer"
    assert sum(p.text == "Roles & Responsibilities:" for p in doc.paragraphs) == 3
    assert sum(p.text.startswith("Skills: ") for p in doc.paragraphs) == 3
    assert sum(p.text.startswith("Environment: ") for p in doc.paragraphs) == 0
    assert not any(p.paragraph_format.page_break_before is True for p in doc.paragraphs)


def _generated_payload(long_content=False):
    extra = (
        " This additional detail verifies that the renderer keeps the native paragraph formatting even when a bullet wraps."
        if long_content
        else ""
    )
    skills = {
        "Programming Languages": ["Python", "SQL"],
        "Cloud Platforms (AWS)": ["AWS Glue", "Amazon S3"],
        "Cloud Platforms (Azure)": ["Azure Data Factory", "ADLS Gen2"],
        "Data Integration & Orchestration": ["Airflow", "dbt"],
    }
    return {
        "summary": (
            "Senior Data Engineer focused on Python, SQL, and reliable data pipelines for enterprise analytics."
            + extra
            + "\n\n"
            "Builds governed batch and streaming workflows while preserving production reliability and clear data models."
            + extra
        ),
        "skills": skills,
        "experience": [
            {
                "company": "Fidelity Investments",
                "bullets": [
                    f"Built Python and SQL data pipelines for reliable financial data processing workflow {i}.{extra}"
                    for i in range(1, 11)
                ],
                "skills_used": ["Python", "SQL"],
            },
            {
                "company": "Cigna Healthcare",
                "bullets": [
                    f"Developed Python and SQL data integrations for healthcare workflow {i}.{extra}"
                    for i in range(1, 9)
                ],
                "skills_used": ["Python", "SQL"],
            },
            {
                "company": "Target Corporation",
                "bullets": [
                    f"Implemented Python and SQL batch processing for retail workflow {i}.{extra}"
                    for i in range(1, 9)
                ],
                "skills_used": ["Python", "SQL"],
            },
        ],
    }


def test_jd_tailored_renderer_keeps_word_format_and_skills_footers(monkeypatch, tmp_path):
    monkeypatch.setattr(formatter, "ROOT", tmp_path)
    monkeypatch.setattr(formatter, "WORD_FORMAT_PATH", formatter.WORD_FORMAT_PATH)
    job = SimpleNamespace(company="Example Company", title="Senior Data Engineer")
    path = formatter.render_llm_resume(job, {}, _generated_payload(), output_dir="resumes")
    result = formatter.validate_master_format_contract(path)
    assert result["passed"], result["reasons"]
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "Skills: Python, SQL" in text
    assert "Environment:" not in text
    assert not any(p.paragraph_format.page_break_before is True for p in Document(path).paragraphs)


def test_renderer_preserves_master_paragraph_format_when_content_wraps(monkeypatch, tmp_path):
    monkeypatch.setattr(formatter, "ROOT", tmp_path)
    monkeypatch.setattr(formatter, "WORD_FORMAT_PATH", formatter.WORD_FORMAT_PATH)
    job = SimpleNamespace(company="Example Company", title="Senior Data Engineer")
    path = formatter.render_llm_resume(job, {}, _generated_payload(long_content=True), output_dir="resumes")
    result = formatter.validate_master_format_contract(path)
    assert result["passed"], result["reasons"]
    assert result["content_length_policy"] == "compact_master_like_layout"
