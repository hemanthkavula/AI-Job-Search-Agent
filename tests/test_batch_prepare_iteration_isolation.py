import json
from pathlib import Path

from app import batch_prepare


def test_early_failure_on_second_job_never_deletes_first_jobs_resume(monkeypatch, tmp_path):
    report = tmp_path / "finalized.json"
    output = tmp_path / "manifest.json"
    rows = []
    for idx in (1, 2):
        raw = {
            "external_id": f"lever:{idx}",
            "source": "lever",
            "company_key": f"Company {idx}",
            "title": "Data Engineer",
            "url": f"https://jobs.example.com/{idx}",
            "original_url": f"https://jobs.example.com/{idx}",
            "description": "Responsibilities: build data pipelines with Spark and SQL.",
            "description_usable": True,
            "employment_type": "Full-time",
            "location": "United States",
        }
        rows.append({
            "action": "FINAL_JD_VERIFIED",
            "job": raw,
            "eligibility": {"experience": {}, "sponsorship": {}},
        })
    report.write_text(json.dumps({"results": rows}), encoding="utf-8")

    monkeypatch.setattr(batch_prepare, "load_profile", lambda: {
        "summary_source": [], "skill_categories": {}, "experience": []
    })

    calls = {"n": 0}
    def coverage(job, profile):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("second job fails before rendering")
        return {"target_count": 2, "must_cover_terms": ["Spark", "SQL"], "preferred_terms": []}
    monkeypatch.setattr(batch_prepare, "build_coverage_plan", coverage)

    first_docx = tmp_path / "approved-first.docx"
    first_pdf = tmp_path / "approved-first.pdf"
    first_docx.write_bytes(b"docx")
    first_pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(batch_prepare, "generate_with_llm", lambda job, profile, audit_feedback=None, coverage_plan=None: {"summary":"x","skills":{"Languages":["Python"]},"experience":[]})
    monkeypatch.setattr(batch_prepare, "_render_draft", lambda job, profile, payload: str(tmp_path / "draft.docx"))
    monkeypatch.setattr(batch_prepare, "ats_audit", lambda job, profile, resume: {"passed":True,"quality_gates":{}})
    monkeypatch.setattr(batch_prepare, "_promote_approved_resume", lambda path: str(first_docx))
    monkeypatch.setattr(batch_prepare, "convert_docx_to_pdf_detailed", lambda path, attempts=2: {
        "pdf_path": str(first_pdf), "attempts": 1, "reason": "ok", "renderer": "test"
    })
    monkeypatch.setattr(batch_prepare, "validate_docx_pdf_parity", lambda docx, pdf: {"passed": True})

    manifest = batch_prepare.prepare(str(report), str(output))

    assert manifest[0]["next_action"] == "READY_TO_APPLY"
    assert first_docx.exists()
    assert first_pdf.exists()
    assert manifest[1]["next_action"] == "HOLD_RESUME_ERROR"
    assert manifest[1]["resume_path"] is None
    assert manifest[1]["pdf_path"] is None
