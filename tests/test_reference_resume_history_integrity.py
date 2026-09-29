from pathlib import Path
from types import SimpleNamespace
from docx import Document

from app.reference_resume_formatter import render_llm_resume


def _profile():
    return {
        "name":"Candidate","contact":{},
        "experience":[
            {"company":"Fidelity Investments","location":"Jersey City, NJ","title":"Senior Data Engineer","dates":"Jan 2025 – Present"},
            {"company":"Cigna Healthcare","location":"Bangalore","title":"Data Engineer","dates":"Jan 2022 – Dec 2023"},
            {"company":"Target Corporation","location":"Bangalore","title":"Data Engineer","dates":"Jan 2020 – Dec 2021"},
        ],
        "education":[{"degree":"MS Computer Science","school":"Rowan University","location":"Glassboro, NJ","start":"2024","end":"2025"}],
    }


def test_renderer_uses_canonical_history_order_and_rejects_extra_employers(tmp_path):
    generated={
        "summary":"Tailored summary","skills":{"Languages":["Python"]},
        "experience":[
            {"company":"Target Corporation","title":"FAKE TITLE","dates":"FAKE DATES","bullets":["Target tailored bullet"]},
            {"company":"Invented Employer","bullets":["must never render"]},
            {"company":"Fidelity Investments","bullets":["Fidelity tailored bullet"]},
            {"company":"Fidelity Investments","bullets":["duplicate must never render"]},
        ],
    }
    job=SimpleNamespace(company="Example",title="Senior Data Engineer")
    path=render_llm_resume(job,_profile(),generated,output_dir=str(tmp_path))
    text="\n".join(p.text for p in Document(path).paragraphs)
    assert text.index("Fidelity Investments") < text.index("Cigna Healthcare") < text.index("Target Corporation")
    assert "Invented Employer" not in text
    assert "FAKE TITLE" not in text and "FAKE DATES" not in text
    assert "duplicate must never render" not in text
    assert "Senior Data Engineer" in text
    assert "Jan 2025 – Present" in text
    assert "Jan 2022 – Dec 2023" in text
    assert "Jan 2020 – Dec 2021" in text
