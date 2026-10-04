import json
from pathlib import Path
from types import SimpleNamespace

from docx import Document

import app.reference_resume_formatter as formatter
from app.llm_resume_writer import build_prompt
from app.master_resume import fixed_personal_facts, load_master_resume, master_resume_payload


EXPECTED_SHA256="81b8a8ec35b1a21e81671d2f386aa391bbeb170e6334c0336874fd6d323353e2"


def test_uploaded_resume_is_authoritative_master_record():
    master=load_master_resume()
    assert master["source"]["authority"]=="user_uploaded_master"
    assert master["source"]["sha256"]==EXPECTED_SHA256
    assert master["source"]["pages"]==2
    assert [len(x["bullets"]) for x in master["experience"]]==[10,8,8]
    assert master["style"]["font"]=="Calibri"
    assert master["style"]["body_pt"]==10.0


def test_fixed_personal_facts_exclude_all_master_technical_content():
    facts=fixed_personal_facts()
    serialized=json.dumps(facts).lower()
    for forbidden in ("pyspark","snowflake","databricks","kafka","terraform","great expectations","environment","bullets"):
        assert forbidden not in serialized
    assert facts["name"]=="Hemanth Kavula"
    assert [x["company"] for x in facts["employment_history"]]==[
        "Fidelity Investments","Cigna Healthcare","Target Corporation"
    ]


def test_tailoring_prompt_ignores_profile_technical_fields():
    job=SimpleNamespace(company="Example",title="Data Engineer",description="Build Python and SQL ETL pipelines with Airflow.")
    contaminated_profile={
        "skills":["SECRET_MASTER_TOOL"],
        "summary_source":["SECRET MASTER SUMMARY"],
        "experience":[{"evidence":["SECRET MASTER BULLET"]}],
    }
    prompt=build_prompt(job,contaminated_profile,coverage_plan={"target_count":3,"must_cover_terms":["Python","SQL","Airflow"]})
    serialized=json.dumps(prompt)
    assert "SECRET_MASTER_TOOL" not in serialized
    assert "SECRET MASTER SUMMARY" not in serialized
    assert "SECRET MASTER BULLET" not in serialized
    policy=prompt["technical_source_policy"]
    assert policy["job_description_is_primary_technical_source"] is True
    assert policy["employer_cloud_credibility_exception_only"] is True
    assert prompt["employer_cloud_credibility_policy"]["hard_constraint"] is True


def test_master_payload_is_exact_zero_target_content():
    payload=master_resume_payload()
    assert payload["_master_mode"] is True
    assert len(payload["experience"][0]["bullets"])==10
    assert len(payload["experience"][1]["bullets"])==8
    assert len(payload["experience"][2]["bullets"])==8
    assert "dbt transformation models" in payload["experience"][0]["bullets"][4]
    assert "AI/ML-driven analytics" in payload["experience"][0]["bullets"][6]


def test_renderer_reproduces_master_format_contract(monkeypatch,tmp_path):
    monkeypatch.setattr(formatter,"ROOT",tmp_path)
    job=SimpleNamespace(company="Example Company",title="Data Engineer")
    path=formatter.render_llm_resume(job,{},master_resume_payload(),output_dir="resumes")
    result=formatter.validate_master_format_contract(path)
    assert result["passed"],result["reasons"]

    doc=Document(path)
    assert doc.paragraphs[0].text=="Hemanth Kavula"
    assert doc.paragraphs[1].text=="Senior Data Engineer"
    assert sum(p.text=="Roles & Responsibilities:" for p in doc.paragraphs)==3
    assert sum(p.text.startswith("Environment: ") for p in doc.paragraphs)==3


def test_tailored_renderer_keeps_master_format_but_not_master_content(monkeypatch,tmp_path):
    monkeypatch.setattr(formatter,"ROOT",tmp_path)
    job=SimpleNamespace(company="Example Company",title="Senior Data Engineer")
    generated={
        "summary":"Senior Data Engineer focused on Python, SQL, and Airflow for reliable data pipelines. Designs ETL workflows and production data integrations.\n\nBuilds maintainable batch processing and data quality patterns. Partners with engineering teams to deliver scalable data platforms.",
        "skills":{
            "Programming & Query Languages":["Python","SQL"],
            "ETL/ELT & Orchestration":["Airflow","ETL"],
            "Data Quality":["Data Quality"],
        },
        "experience":[
            {"company":"Fidelity Investments","bullets":[f"Built Python and SQL ETL pipelines with Airflow for reliable data processing workflow {i}." for i in range(1,11)],"environment":"Python, SQL, Airflow, ETL"},
            {"company":"Cigna Healthcare","bullets":[f"Developed Python and SQL data integrations with Airflow and data quality controls for workflow {i}." for i in range(1,9)],"environment":"Python, SQL, Airflow, Data Quality"},
            {"company":"Target Corporation","bullets":[f"Implemented Python and SQL batch processing with Airflow for maintainable ETL workflow {i}." for i in range(1,9)],"environment":"Python, SQL, Airflow, ETL"},
        ],
    }
    path=formatter.render_llm_resume(job,{},generated,output_dir="resumes")
    result=formatter.validate_master_format_contract(path)
    assert result["passed"],result["reasons"]
    text="\n".join(p.text for p in Document(path).paragraphs)
    assert "Great Expectations (70+ rules)" not in text
    assert "~400–500GB" not in text
    assert "Python, SQL, Airflow" in text
