from types import SimpleNamespace

import app.ats_audit as aa


def test_empty_required_target_set_is_full_coverage(monkeypatch):
    monkeypatch.setattr(aa, "document_text", lambda _: "Data Engineer professional summary technical skills professional experience education")
    monkeypatch.setattr(aa, "build_coverage_plan", lambda job, profile: {
        "must_cover_terms": [],
        "preferred_terms": ["Requirements Gathering"],
        "alternative_terms": [],
    })

    class P:
        text = ""
        style = None

    class D:
        paragraphs = [P()]

    monkeypatch.setattr(aa, "Document", lambda _: D())
    job = SimpleNamespace(title="Data Engineer", description="hands-on data engineering")
    result = aa.ats_audit(job, {}, "unused.docx")

    assert result["keyword_coverage"] == 100
    assert result["experience_depth_coverage"] == 100
    assert result["quality_gates"]["experience_depth"] is True
