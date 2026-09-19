from pathlib import Path

import app.batch_prepare as bp


def test_failed_resume_cleanup_removes_entire_job_folder(tmp_path):
    folder = tmp_path / "generated" / "resumes" / "Example_Data_Engineer"
    folder.mkdir(parents=True)
    docx = folder / "resume.docx"
    pdf = folder / "resume.pdf"
    temp = folder / "conversion.tmp"
    docx.write_bytes(b"docx")
    pdf.write_bytes(b"pdf")
    temp.write_bytes(b"tmp")

    bp._discard_resume_artifact(docx)

    assert not folder.exists()


def test_failed_resume_cleanup_is_safe_when_artifact_already_gone(tmp_path):
    missing = tmp_path / "generated" / "resumes" / "Gone" / "resume.docx"
    bp._discard_resume_artifact(missing)
    assert not missing.parent.exists()
