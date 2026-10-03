import json
from pathlib import Path
from types import SimpleNamespace
from docx import Document
from docx.shared import Pt
from app.batch_prepare import _base_resume_payload
from app.reference_resume_formatter import render_llm_resume
from app.llm_resume_writer import SYSTEM_PROMPT, build_prompt

ROOT=Path(__file__).resolve().parents[1]

def _profile():
    return json.loads((ROOT/"data/candidate_profile.json").read_text(encoding="utf-8"))

def test_uploaded_master_is_the_profile_baseline():
    p=_profile(); exp={x["company"]:x for x in p["experience"]}
    assert p["master_resume_reference"]["effective_date"]=="2026-10-03"
    assert p["master_resume_reference"]["bullet_counts"]=={"Fidelity Investments":10,"Cigna Healthcare":8,"Target Corporation":8}
    assert [len(exp[c]["evidence"]) for c in ("Fidelity Investments","Cigna Healthcare","Target Corporation")]==[10,8,8]
    assert any("dbt transformation models" in x for x in exp["Fidelity Investments"]["evidence"])
    assert any("AI/ML-driven analytics" in x for x in exp["Fidelity Investments"]["evidence"])
    assert any("~120–180GB/day" in x for x in exp["Target Corporation"]["evidence"])
    assert len(p["summary_source"])==2
    assert p["skill_categories"]["Programming Languages"]==["Python","SQL","Scala"]

def test_base_payload_preserves_master_paragraphs_and_emphasis():
    p=_profile(); payload=_base_resume_payload(p)
    assert "\n\n" in payload["summary"]
    assert payload["summary_emphasis"]==p["summary_emphasis"]
    assert len(payload["experience"][0]["bullet_emphasis"])==10

def test_formatter_matches_master_visual_contract(tmp_path):
    p=_profile(); payload=_base_resume_payload(p)
    path=render_llm_resume(SimpleNamespace(company="Example",title="Senior Data Engineer"),p,payload,output_dir=str(tmp_path))
    doc=Document(path); paras=doc.paragraphs
    assert doc.styles["Normal"].font.name=="Calibri"
    assert doc.styles["Normal"].font.size==Pt(10)
    assert paras[0].runs[0].font.size==Pt(18)
    assert paras[1].runs[0].font.size==Pt(13)
    summary_heading=next(x for x in paras if x.text=="PROFESSIONAL SUMMARY")
    assert summary_heading.runs[0].font.size==Pt(12)
    assert summary_heading.runs[0].font.color.rgb is not None
    summary_idx=paras.index(summary_heading)
    summary_paras=[]
    for x in paras[summary_idx+1:]:
        if x.text=="TECHNICAL SKILLS":break
        if x.text.strip():summary_paras.append(x)
    assert len(summary_paras)==2
    assert any(r.bold and "financial services" in r.text for x in summary_paras for r in x.runs)
    assert sum(x.text=="Roles & Responsibilities:" for x in paras)==3
    assert sum(x.text.startswith("Environment: ") for x in paras)==3
    current=None;counts={"Fidelity Investments":0,"Cigna Healthcare":0,"Target Corporation":0}
    fidelity_bullets=[]
    for x in paras:
        if x.text.startswith("Fidelity Investments"):current="Fidelity Investments"
        elif x.text.startswith("Cigna Healthcare"):current="Cigna Healthcare"
        elif x.text.startswith("Target Corporation"):current="Target Corporation"
        elif current and x.style and "List Bullet" in x.style.name:
            counts[current]+=1
            if current=="Fidelity Investments":fidelity_bullets.append(x)
    assert counts=={"Fidelity Investments":10,"Cigna Healthcare":8,"Target Corporation":8}
    assert fidelity_bullets[8].paragraph_format.page_break_before is True
    assert any(r.bold and "~2.5–3M" in r.text for r in fidelity_bullets[0].runs)
    education=next(x for x in paras if x.text=="EDUCATION")
    assert education.runs[0].font.size==Pt(12)

def test_llm_contract_uses_master_density_and_emphasis_schema():
    assert "10 Fidelity bullets, 8 Cigna bullets, and 8 Target bullets" in SYSTEM_PROMPT
    assert "VISUAL EMPHASIS CONTRACT" in SYSTEM_PROMPT
    p=_profile();job=SimpleNamespace(company="Example",title="Data Engineer",description="Python SQL Databricks")
    prompt=build_prompt(job,p,coverage_plan={})
    schema=prompt["output_schema"]
    assert "summary_emphasis" in schema
    assert "bullet_emphasis" in schema["experience"][0]
    assert prompt["quality_rules"]["fidelity_bullets"]==10
    assert prompt["quality_rules"]["target_metric_bullets_max"]==1
