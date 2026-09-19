from pathlib import Path

from app import pdf_export


def test_detailed_conversion_reports_recovery_attempt(monkeypatch, tmp_path):
    docx = tmp_path / "resume.docx"
    docx.write_bytes(b"approved-docx")
    calls = []

    def fake_attempt(src, target):
        calls.append((src, target))
        if len(calls) == 1:
            return False, "temporary renderer failure"
        target.write_bytes(b"%PDF-test")
        return True, "ok"

    monkeypatch.setattr(pdf_export, "_conversion_attempt", fake_attempt)
    monkeypatch.setattr(pdf_export.time, "sleep", lambda _: None)

    result = pdf_export.convert_docx_to_pdf_detailed(str(docx), attempts=2)

    assert result["pdf_path"] == str(docx.with_suffix(".pdf").resolve())
    assert result["attempts"] == 2
    assert result["reason"] is None
    assert result["renderer"] == "libreoffice_headless"
    assert calls[0][0] == calls[1][0]


def test_detailed_conversion_persists_final_failure_reason(monkeypatch, tmp_path):
    docx = tmp_path / "resume.docx"
    docx.write_bytes(b"approved-docx")
    reasons = iter(["first failure", "second failure"])

    monkeypatch.setattr(
        pdf_export,
        "_conversion_attempt",
        lambda src, target: (False, next(reasons)),
    )
    monkeypatch.setattr(pdf_export.time, "sleep", lambda _: None)

    result = pdf_export.convert_docx_to_pdf_detailed(str(docx), attempts=2)

    assert result["pdf_path"] is None
    assert result["attempts"] == 2
    assert result["reason"] == "second failure"
