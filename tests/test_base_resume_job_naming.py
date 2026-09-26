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


def test_incomplete_dice_jd_uses_master_resume_without_llm(tmp_path, monkeypatch):
    import json

    description="Requirements: Python SQL AWS Glue S3 ETL pipelines and production support."
    report={"results":[{
        "action":"FINAL_JD_VERIFIED",
        "eligibility":{"experience":{"category":"EXPERIENCE_MATCH"},"sponsorship":{"category":"SPONSORSHIP_UNKNOWN"}},
        "job":{
            "external_id":"dice:good-short",
            "source":"dice",
            "company_key":"Example",
            "title":"Data Engineer",
            "location":"United States",
            "employment_type":"Full-Time",
            "url":"https://www.dice.com/job-detail/good-short",
            "original_url":"https://www.dice.com/job-detail/good-short",
            "description":description,
            "description_complete":False,
            "description_usable":True,
            "tailoring_mode":"BASE_RESUME_CONSERVATIVE",
            "application_route":"DICE",
            "ats_provider":"dice",
        }
    }]}
    inp=tmp_path/"finalized.json"
    out=tmp_path/"manifest.json"
    inp.write_text(json.dumps(report),encoding="utf-8")
    profile={
        "summary_source":["Data engineer."],
        "skill_categories":{"Languages":["Python","SQL"]},
        "experience":[{"company":"Example","evidence":["Built data pipelines."]}],
    }
    monkeypatch.setattr(batch_prepare,"load_profile",lambda:profile)
    monkeypatch.setattr(batch_prepare,"build_coverage_plan",lambda job,profile:{
        "target_count":4,"must_cover_terms":["Python","SQL"],"preferred_terms":["AWS Glue","S3"]
    })
    monkeypatch.setattr(batch_prepare,"generate_with_llm",lambda *a,**k:(_ for _ in ()).throw(AssertionError("LLM must not be called for incomplete JD fallback")))
    monkeypatch.setattr(batch_prepare,"_render_base_resume",lambda job,profile:str(tmp_path/"master.docx"))
    monkeypatch.setattr(batch_prepare,"_promote_approved_resume",lambda path:path)
    monkeypatch.setattr(batch_prepare,"convert_docx_to_pdf_detailed",lambda path,attempts=2:{"pdf_path":str(tmp_path/"master.pdf"),"attempts":1,"reason":"ok","renderer":"test"})
    monkeypatch.setattr(batch_prepare,"validate_docx_pdf_parity",lambda docx,pdf:{"passed":True,"reason":"ok"})

    rows=batch_prepare.prepare(str(inp),str(out))

    assert len(rows)==1
    assert rows[0]["next_action"]=="READY_TO_APPLY"
    assert rows[0]["tailoring_mode"]=="BASE_RESUME_CONSERVATIVE"
    # Incomplete Dice JDs must retain the non-LLM fallback provenance in the manifest.
    assert rows[0]["ats_audit"]["generation_source"]=="master_resume_incomplete_jd"
    assert rows[0]["ats_audit"]["generation_attempts"]==0
