from app.production_cycle import _is_real_pdf


def test_production_manifest_pdf_gate_checks_signature(tmp_path):
    fake=tmp_path/"fake.pdf"
    fake.write_text("not a pdf",encoding="utf-8")
    assert _is_real_pdf(fake) is False
    real=tmp_path/"real.pdf"
    real.write_bytes(b"%PDF-1.7\nminimal fixture")
    assert _is_real_pdf(real) is True
    assert _is_real_pdf(tmp_path/"missing.pdf") is False
