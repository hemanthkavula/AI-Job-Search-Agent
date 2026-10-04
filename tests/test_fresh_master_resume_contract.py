import json
from types import SimpleNamespace

from docx import Document

import app.reference_resume_formatter as formatter
from app.llm_resume_writer import build_prompt
from app.master_resume import fixed_personal_facts, load_master_resume, master_resume_payload


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
    assert record["content_budget"]["pdf_pages_required"] == 2


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


def test_tailoring_prompt_uses_jd_not_template_technical_content():
    job = SimpleNamespace(
        company="Example",
        title="Data Engineer",
        description=(
            "Build Python and SQL ETL pipelines with Airflow. Required hands-on Python, SQL, and Airflow."
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
            "target_count": 3,
            "must_cover_terms": ["Python", "SQL", "Airflow"],
            "targeted_terms": ["Python", "SQL", "Airflow"],
            "requirements": [
                {"term": "Python", "classification": "required"},
                {"term": "SQL", "classification": "required"},
                {"term": "Airflow", "classification": "required"},
            ],
        },
    )
    serialized = json.dumps(prompt)
    assert "PROFILE_ONLY_TOOL" not in serialized
    assert "PROFILE ONLY SUMMARY" not in serialized
    assert "PROFILE ONLY BULLET" not in serialized
    assert "authoritative_master_resume_base" not in prompt
    for forbidden_template_tech in (
        "Great Expectations",
        "Kinesis",
        "Azure Purview",
        "Power BI",
        "Tableau",
    ):
        assert forbidden_template_tech not in serialized
    policy = prompt["technical_source_policy"]
    assert policy["allowed_technical_sources"] == [
        "current_job_description",
        "pre_generation_coverage_plan",
    ]
    assert policy["word_or_pdf_template_is_format_only"] is True
    assert policy["template_technical_content_must_not_be_used"] is True
    assert policy["every_technology_requires_current_jd_evidence"] is True
    assert policy["profile_argument_is_not_a_technical_source"] is True
    assert prompt["employer_cloud_credibility_policy"]["hard_constraint"] is True


def test_master_payload_remains_zero_target_fallback_only():
    payload = master_resume_payload()
    assert payload["_master_mode"] is True
    assert len(payload["experience"][0]["bullets"]) == 10
    assert len(payload["experience"][1]["bullets"]) == 8
    assert len(payload["experience"][2]["bullets"]) == 8
    assert "dbt transformation models" in payload["experience"][0]["bullets"][4]
    assert "AI/ML-driven analytics" in payload["experience"][0]["bullets"][6]


def test_renderer_reproduces_uploaded_word_format_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(formatter, "ROOT", tmp_path)
    monkeypatch.setattr(formatter, "WORD_FORMAT_PATH", formatter.WORD_FORMAT_PATH)
    job = SimpleNamespace(company="Example Company", title="Data Engineer")
    path = formatter.render_llm_resume(
        job, {}, master_resume_payload(), output_dir="resumes"
    )
    result = formatter.validate_master_format_contract(path)
    assert result["passed"], result["reasons"]
    assert result["format_authority"] == "user_uploaded_word_format_template"
    doc = Document(path)
    assert doc.paragraphs[0].text == "Hemanth Kavula"
    assert doc.paragraphs[1].text == "Senior Data Engineer"
    assert sum(p.text == "Roles & Responsibilities:" for p in doc.paragraphs) == 3
    assert sum(p.text.startswith("Environment: ") for p in doc.paragraphs) == 3
    assert not any(p.paragraph_format.page_break_before is True for p in doc.paragraphs)
    assert not any(p.paragraph_format.keep_with_next is True for p in doc.paragraphs)


def test_jd_tailored_renderer_keeps_word_format_and_content_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(formatter, "ROOT", tmp_path)
    monkeypatch.setattr(formatter, "WORD_FORMAT_PATH", formatter.WORD_FORMAT_PATH)
    job = SimpleNamespace(company="Example Company", title="Senior Data Engineer")
    generated = {
        "summary": (
            "Senior Data Engineer focused on Python, SQL, and Airflow for reliable data pipelines and production integrations. Designs maintainable ETL workflows and data-quality controls.\n\n"
            "Builds batch and orchestration patterns with Python, SQL, and Airflow. Partners with engineering teams to deliver reliable, governed data products."
        ),
        "skills": {
            "Programming & Query Languages": ["Python", "SQL"],
            "ETL/ELT & Orchestration": ["Airflow", "ETL"],
            "Data Quality": ["Data Quality"],
        },
        "experience": [
            {
                "company": "Fidelity Investments",
                "bullets": [
                    f"Built Python and SQL ETL pipelines with Airflow for reliable financial data processing workflow {i}."
                    for i in range(1, 11)
                ],
                "environment": "Python, SQL, Airflow, ETL",
            },
            {
                "company": "Cigna Healthcare",
                "bullets": [
                    f"Developed Python and SQL data integrations with Airflow and data quality controls for healthcare workflow {i}."
                    for i in range(1, 9)
                ],
                "environment": "Python, SQL, Airflow, Data Quality",
            },
            {
                "company": "Target Corporation",
                "bullets": [
                    f"Implemented Python and SQL batch processing with Airflow for maintainable retail ETL workflow {i}."
                    for i in range(1, 9)
                ],
                "environment": "Python, SQL, Airflow, ETL",
            },
        ],
    }
    path = formatter.render_llm_resume(job, {}, generated, output_dir="resumes")
    result = formatter.validate_master_format_contract(path)
    assert result["passed"], result["reasons"]
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "Python, SQL, Airflow" in text
    assert not any(p.paragraph_format.page_break_before is True for p in Document(path).paragraphs)
