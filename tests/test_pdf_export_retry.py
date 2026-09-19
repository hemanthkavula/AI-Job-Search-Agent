from pathlib import Path

import app.pdf_export as pdf_export


def test_pdf_conversion_retries_same_docx(monkeypatch,tmp_path):
    src=tmp_path/"resume.docx"
    src.write_bytes(b"docx")
    calls=[]

    def fake_attempt(got_src,target):
        calls.append((got_src,target))
        if len(calls)==1:
            return False,"temporary render failure"
        target.write_bytes(b"%PDF-test")
        return True,"ok"

    monkeypatch.setattr(pdf_export,"_conversion_attempt",fake_attempt)
    monkeypatch.setattr(pdf_export.time,"sleep",lambda _:None)

    result=pdf_export.convert_docx_to_pdf(str(src),attempts=2)

    assert result==str(src.with_suffix(".pdf"))
    assert len(calls)==2
    assert calls[0][0]==calls[1][0]==src.resolve()
    assert calls[0][1]==calls[1][1]==src.resolve().with_suffix(".pdf")


def test_pdf_conversion_does_not_claim_success_without_pdf(monkeypatch,tmp_path):
    src=tmp_path/"resume.docx"
    src.write_bytes(b"docx")
    monkeypatch.setattr(
        pdf_export,
        "_conversion_attempt",
        lambda got_src,target:(False,"LibreOffice exited successfully but PDF was not created"),
    )
    monkeypatch.setattr(pdf_export.time,"sleep",lambda _:None)

    assert pdf_export.convert_docx_to_pdf(str(src),attempts=2) is None
