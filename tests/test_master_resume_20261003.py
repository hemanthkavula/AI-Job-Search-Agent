import json
from pathlib import Path
from types import SimpleNamespace

from docx import Document
from docx.shared import Pt

from app.batch_prepare import _base_resume_payload
from app.reference_resume_formatter import (
    render_llm_resume,
    validate_master_format_contract,
)
from app.llm_resume_writer import SYSTEM_PROMPT, build_prompt

ROOT = Path(__file__).resolve().parents[1]


def _profile():
    return json.loads((ROOT / "data/candidate_profile.json").read_text(encoding="utf-8"))


def test_uploaded_master_is_the_profile_baseline():
    p = _profile()
    exp = {x["company"]: x for x in p["experience"]}
    assert p["master_resume_reference"]["effective_date"] == "2026-10-03"
    assert p["master_resume_reference"]["layout_version"] == "master-2026-10-03"
    assert p["master_resume_reference"]["bullet_counts"] == {
        "Fidelity Investments": 10,
        "Cigna Healthcare": 8,
        "Target Corporation": 8,
    }
    assert [
        len(exp[c]["evidence"])
        for c in ("Fidelity Investments", "Cigna Healthcare", "Target Corporation")
    ] == [10, 8, 8]
    assert any("dbt transformation models" in x for x in exp["Fidelity Investments"]["evidence"])
    assert any("AI/ML-driven analytics" in x for x in exp["Fidelity Investments"]["evidence"])
    assert any("~120–180GB/day" in x for x in exp["Target Corporation"]["evidence"])
    assert len(p["summary_source"]) == 2
    assert p["skill_categories"]["Programming Languages"] == ["Python", "SQL", "Scala"]


def test_base_payload_preserves_master_paragraphs_and_emphasis():
    p = _profile()
    payload = _base_resume_payload(p)
    assert "\n\n" in payload["summary"]
    assert payload["summary_emphasis"] == p["summary_emphasis"]
    assert len(payload["experience"][0]["bullet_emphasis"]) == 10


def test_formatter_matches_master_visual_contract(tmp_path):
    p = _profile()
    style = p["master_resume_reference"]["style"]
    payload = _base_resume_payload(p)
    path = render_llm_resume(
        SimpleNamespace(company="Example", title="Senior Data Engineer"),
        p,
        payload,
        output_dir=str(tmp_path),
    )
    doc = Document(path)
    paras = doc.paragraphs

    assert doc.styles["Normal"].font.name == style["font"]
    assert doc.styles["Normal"].font.size == Pt(style["body_pt"])
    assert paras[0].runs[0].font.size == Pt(style["name_pt"])
    assert paras[1].runs[0].font.size == Pt(style["headline_pt"])
    assert round(doc.sections[0].top_margin.inches, 2) == 0.55
    assert round(doc.sections[0].bottom_margin.inches, 2) == 0.42
    assert round(doc.sections[0].left_margin.inches, 2) == 0.50
    assert round(doc.sections[0].right_margin.inches, 2) == 0.50

    summary_heading = next(x for x in paras if x.text == "PROFESSIONAL SUMMARY")
    assert summary_heading.runs[0].font.size == Pt(style["section_heading_pt"])
    assert str(summary_heading.runs[0].font.color.rgb) == style["accent_hex"]

    summary_idx = paras.index(summary_heading)
    summary_paras = []
    for x in paras[summary_idx + 1 :]:
        if x.text == "TECHNICAL SKILLS":
            break
        if x.text.strip():
            summary_paras.append(x)
    assert len(summary_paras) == 2
    assert all(
        run.font.size == Pt(style["summary_pt"])
        for paragraph in summary_paras
        for run in paragraph.runs
        if run.text
    )
    assert any(
        run.bold and "financial services" in run.text
        for paragraph in summary_paras
        for run in paragraph.runs
    )

    assert sum(x.text == "Roles & Responsibilities:" for x in paras) == 3
    assert sum(x.text.startswith("Environment: ") for x in paras) == 3

    current = None
    counts = {"Fidelity Investments": 0, "Cigna Healthcare": 0, "Target Corporation": 0}
    fidelity_bullets = []
    for x in paras:
        if x.text.startswith("Fidelity Investments"):
            current = "Fidelity Investments"
        elif x.text.startswith("Cigna Healthcare"):
            current = "Cigna Healthcare"
        elif x.text.startswith("Target Corporation"):
            current = "Target Corporation"
        elif current and x.style and "List Bullet" in x.style.name:
            counts[current] += 1
            if current == "Fidelity Investments":
                fidelity_bullets.append(x)

    assert counts == {"Fidelity Investments": 10, "Cigna Healthcare": 8, "Target Corporation": 8}
    assert fidelity_bullets[8].paragraph_format.page_break_before is True
    assert any(run.bold and "~2.5–3M" in run.text for run in fidelity_bullets[0].runs)

    education = next(x for x in paras if x.text == "EDUCATION")
    assert education.runs[0].font.size == Pt(style["section_heading_pt"])

    validation = validate_master_format_contract(path, p)
    assert validation == {
        "passed": True,
        "reasons": [],
        "layout_version": "master-2026-10-03",
    }


def test_master_style_metadata_drives_renderer(tmp_path):
    p = _profile()
    p["master_resume_reference"]["style"]["name_pt"] = 19
    p["master_resume_reference"]["style"]["section_heading_pt"] = 11
    p["master_resume_reference"]["style"]["accent_hex"] = "234567"
    payload = _base_resume_payload(p)

    path = render_llm_resume(
        SimpleNamespace(company="Example", title="Senior Data Engineer"),
        p,
        payload,
        output_dir=str(tmp_path),
    )
    doc = Document(path)
    summary_heading = next(x for x in doc.paragraphs if x.text == "PROFESSIONAL SUMMARY")

    assert doc.paragraphs[0].runs[0].font.size == Pt(19)
    assert summary_heading.runs[0].font.size == Pt(11)
    assert str(summary_heading.runs[0].font.color.rgb) == "234567"
    assert validate_master_format_contract(path, p)["passed"] is True


def test_format_validator_rejects_visual_drift(tmp_path):
    p = _profile()
    payload = _base_resume_payload(p)
    path = render_llm_resume(
        SimpleNamespace(company="Example", title="Senior Data Engineer"),
        p,
        payload,
        output_dir=str(tmp_path),
    )

    doc = Document(path)
    doc.paragraphs[0].runs[0].font.size = Pt(20)
    doc.save(path)

    validation = validate_master_format_contract(path, p)
    assert validation["passed"] is False
    assert "name_size_mismatch" in validation["reasons"]


def test_llm_contract_uses_master_density_and_emphasis_schema():
    assert "10 Fidelity bullets, 8 Cigna bullets, and 8 Target bullets" in SYSTEM_PROMPT
    assert "VISUAL EMPHASIS CONTRACT" in SYSTEM_PROMPT
    p = _profile()
    job = SimpleNamespace(company="Example", title="Data Engineer", description="Python SQL Databricks")
    prompt = build_prompt(job, p, coverage_plan={})
    schema = prompt["output_schema"]
    assert "summary_emphasis" in schema
    assert "bullet_emphasis" in schema["experience"][0]
    assert prompt["quality_rules"]["fidelity_bullets"] == 10
    assert prompt["quality_rules"]["target_metric_bullets_max"] == 1
