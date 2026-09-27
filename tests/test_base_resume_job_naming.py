from pathlib import Path
from types import SimpleNamespace

import app.batch_prepare as batch_prepare


def test_base_resume_fallback_uses_current_job_metadata(monkeypatch):
    captured={}

    def fake_render(job,profile,payload,output_dir):
        captured["job"]=job
        captured["profile"]=profile
        captured["payload"]=payload
        captured["output_dir"]=output_dir
        return "generated/resumes/Lennar_Corp_Lead_Data_Engineer/Hemanth_Kavula_Lennar_Corp_Lead_Data_Engineer.docx"

    monkeypatch.setattr(batch_prepare,"render_llm_resume",fake_render)
    job=SimpleNamespace(
        company="Lennar Corp",
        title="Lead Data Engineer",
        description="",
        location="United States",
        employment_type="Full-Time",
        url="https://example.invalid/job",
    )
    profile={
        "summary_source":["Data engineer."],
        "skill_categories":{"Languages":["Python","SQL"]},
        "experience":[{"company":"Example","evidence":["Built data pipelines."]}],
    }

    path=batch_prepare._render_base_resume(job,profile)

    assert captured["job"] is job
    assert captured["output_dir"]=="generated/.resume_drafts"
    assert captured["payload"]==batch_prepare._base_resume_payload(profile)
    assert "Lennar_Corp" in path
    assert "Lead_Data_Engineer" in path


def test_incomplete_but_usable_jd_with_targets_requires_tailoring():
    raw={"tailoring_mode":"BASE_RESUME_CONSERVATIVE","description_usable":True}
    coverage_plan={"target_count":4,"must_cover_terms":["Python","SQL"],"preferred_terms":["AWS Glue","S3"]}
    assert batch_prepare._should_use_master_resume(raw,coverage_plan) is False


def test_zero_target_jd_may_use_master_resume():
    raw={"tailoring_mode":"BASE_RESUME_CONSERVATIVE","description_usable":True}
    assert batch_prepare._should_use_master_resume(raw,{"target_count":0}) is True
