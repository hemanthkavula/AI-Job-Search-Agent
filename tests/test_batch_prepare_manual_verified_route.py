from types import SimpleNamespace
from app import batch_prepare


def test_manual_verified_ats_never_becomes_auto_ready(monkeypatch,tmp_path):
    raw={"external_id":"manatal:1","source":"manatal","company_key":"Example Staffing","title":"Data Engineer",
         "location":"United States","employment_type":"Full-Time","url":"https://example.test/jobs/1",
         "original_url":"https://example.test/jobs/1","ats_provider":"manatal","application_route":"MANUAL_VERIFIED_ATS",
         "manual_application_required":True,"tailoring_mode":"BASE_RESUME_CONSERVATIVE",
         "description":"Responsibilities build data pipelines","description_usable":True}
    report=tmp_path/"finalized.json";out=tmp_path/"manifest.json"
    import json
    report.write_text(json.dumps({"results":[{"action":"FINAL_JD_VERIFIED","job":raw,"eligibility":{"experience":{},"sponsorship":{}}}]}),encoding="utf-8")
    monkeypatch.setattr(batch_prepare,"load_profile",lambda:{"summary_source":[],"skill_categories":{},"experience":[]})
    monkeypatch.setattr(batch_prepare,"build_coverage_plan",lambda job,profile:{"target_count":0,"must_cover_terms":[],"preferred_terms":[]})
    monkeypatch.setattr(batch_prepare,"_render_base_resume",lambda job,profile:str(tmp_path/"draft.docx"))
    monkeypatch.setattr(batch_prepare,"_promote_approved_resume",lambda path:str(tmp_path/"approved.docx"))
    monkeypatch.setattr(batch_prepare,"convert_docx_to_pdf_detailed",lambda path,attempts=2:{"pdf_path":str(tmp_path/"approved.pdf"),"attempts":1,"reason":"ok","renderer":"test"})
    monkeypatch.setattr(batch_prepare,"validate_docx_pdf_parity",lambda docx,pdf:{"passed":True})
    rows=batch_prepare.prepare(str(report),str(out))
    assert rows[0]["next_action"]=="MANUAL_READY_TO_APPLY"
    assert rows[0]["manual_application_required"] is True
