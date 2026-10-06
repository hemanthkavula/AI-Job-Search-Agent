from types import SimpleNamespace

import app.batch_prepare as batch_prepare
import app.pdf_export as pdf_export
from app.llm_resume_writer import build_prompt


def test_density_depth_and_human_scores_are_advisory_not_blocking():
    audit={
        "passed":False,
        "quality_gates":{
            "structure":True,
            "metrics":True,
            "domain_coherence":True,
            "cloud_credibility":True,
            "master_retention":False,
            "content_density":False,
            "repetition":False,
            "human_quality":False,
            "experience_depth":False,
            "discovery":False,
        },
        "internal_ats_score":81,
        "summary_density_ratio":0.318,
        "experience_depth_coverage":42,
    }

    result=batch_prepare._make_quality_heuristics_advisory(audit)

    assert result["passed"] is True
    assert result["blocking_quality_gates"] == []
    assert "content_density" in result["advisory_quality_gates"]
    assert "experience_depth" in result["advisory_quality_gates"]
    assert "human_quality" in result["advisory_quality_gates"]
    assert result["strict_audit_passed"] is False


def test_real_factual_or_structural_issue_can_still_block():
    audit={
        "passed":False,
        "quality_gates":{
            "structure":True,
            "metrics":False,
            "domain_coherence":True,
            "cloud_credibility":True,
            "content_density":False,
        },
    }
    result=batch_prepare._make_quality_heuristics_advisory(audit)
    assert result["passed"] is False
    assert result["blocking_quality_gates"] == ["metrics"]


def test_three_page_pdf_is_rejected_by_hard_master_layout_contract(monkeypatch,tmp_path):
    pdf=tmp_path/"resume.pdf"
    pdf.write_bytes(b"fake-pdf")

    monkeypatch.setattr(
        pdf_export,
        "_docx_signature",
        lambda _: {
            "paragraphs":[
                "PROFESSIONAL SUMMARY",
                "TECHNICAL SKILLS",
                "PROFESSIONAL EXPERIENCE",
                "Fidelity Investments",
                "Cigna Healthcare",
                "Target Corporation",
                "EDUCATION",
            ],
            "sections":[
                "PROFESSIONAL SUMMARY",
                "TECHNICAL SKILLS",
                "PROFESSIONAL EXPERIENCE",
                "EDUCATION",
            ],
        },
    )
    monkeypatch.setattr(
        pdf_export,
        "_pdf_pages_text",
        lambda _: [
            "Professional Summary Technical Skills Professional Experience Fidelity Investments Environment:",
            "Cigna Healthcare Environment:",
            "Target Corporation Environment: Education",
        ],
    )

    result=pdf_export.validate_docx_pdf_parity("ignored.docx",str(pdf))

    assert result["passed"] is False
    assert result["page_count"] == 3
    assert result["required_page_count"] == 2
    assert result["page_count_match"] is False
    assert result["pagination_policy"] == "hard_master_like_two_page_contract"
    assert "exactly 2 pages" in result["reason"]


def test_tailoring_prompt_uses_compact_master_like_structure_and_skills_footer():
    job=SimpleNamespace(
        company="Example",
        title="Data Engineer",
        description="Build Python SQL Airflow pipelines and data quality controls.",
        description_complete=True,
        description_usable=True,
        tailoring_mode="FULL_JD",
    )
    plan={
        "target_count":4,
        "must_cover_terms":["Python","SQL","Airflow","Data Quality"],
        "targeted_terms":["Python","SQL","Airflow","Data Quality"],
        "requirements":[],
    }

    prompt=build_prompt(job,{},coverage_plan=plan)
    contract=prompt["structure_contract"]

    assert contract["summary_paragraphs"] == 2
    assert contract["fidelity_bullets"] == 10
    assert contract["cigna_bullets"] == 8
    assert contract["target_bullets"] == 8
    assert contract["employer_footer_label"] == "Environment"
    assert contract["environment_paragraphs"] is False
    assert contract["compact_master_like_layout"] is True
