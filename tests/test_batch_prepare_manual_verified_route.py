import json
from app import batch_prepare


def test_verified_long_tail_ats_becomes_ready_for_muse(monkeypatch,tmp_path):
    raw={"external_id":"manatal:1","source":"manatal","company_key":"Example Staffing","title":"Data Engineer",
         "location":"United States","employment_type":"Full-Time","url":"https://example.test/jobs/1",
         "original_url":"https://example.test/jobs/1","ats_provider":"manatal","application_route":"EXTERNAL_ATS",
         "tailoring_mode":"FULL_JD","resume_strategy":"FULL","description":"Responsibilities build data pipelines","description_usable":True,"description_complete":True}
    report=tmp_path/"finalized.json";out=tmp_path/"manifest.json"
    report.write_text(json.dumps({"results":[{"action":"FINAL_JD_VERIFIED","job":raw,"eligibility":{"experience":{},"sponsorship":{}}}]}),encoding="utf-8")
    monkeypatch.setattr(batch_prepare,"load_profile",lambda:{"summary_source":[],"skill_categories":{},"experience":[]})
    monkeypatch.setattr(batch_prepare,"build_coverage_plan",lambda job,profile:{"target_count":2,"must_cover_terms":["data pipelines"],"preferred_terms":[]})
    monkeypatch.setattr(batch_prepare,"select_resume_strategy",lambda job,profile:{"strategy":"FULL","coverage_plan":{"target_count":2}})
    monkeypatch.setattr(batch_prepare,"generate_with_llm",lambda job,profile,audit_feedback=None,coverage_plan=None,mode="FULL":{"summary":"x","skills":{"Data Engineering":["data pipelines"]},"experience":[]})
    monkeypatch.setattr(batch_prepare,"_render_draft",lambda job,profile,payload:str(tmp_path/"draft.docx"))
    monkeypatch.setattr(batch_prepare,"ats_audit",lambda job,profile,resume:{"passed":True,"quality_gates":{}})
    monkeypatch.setattr(batch_prepare,"_promote_approved_resume",lambda path:str(tmp_path/"approved.docx"))
    monkeypatch.setattr(batch_prepare,"convert_docx_to_pdf_detailed",lambda path,attempts=2:{"pdf_path":str(tmp_path/"approved.pdf"),"attempts":1,"reason":"ok","renderer":"test"})
    monkeypatch.setattr(batch_prepare,"validate_docx_pdf_parity",lambda docx,pdf:{"passed":True})
    rows=batch_prepare.prepare(str(report),str(out))
    assert rows[0]["next_action"]=="READY_TO_APPLY"
    assert "manual_application_required" not in rows[0]


def test_base_strategy_copies_master_pdf_without_llm(monkeypatch,tmp_path):
    master=tmp_path/"master.pdf"; master.write_bytes(b"%PDF-1.4 exact-master-bytes")
    monkeypatch.setattr(batch_prepare,"MASTER_RESUME_PATH",str(master))
    import hashlib
    monkeypatch.setattr(batch_prepare,"MASTER_RESUME_SHA256",hashlib.sha256(master.read_bytes()).hexdigest())
    monkeypatch.setattr(batch_prepare,"FINAL_RESUME_DIR",str(tmp_path/"resumes"))
    monkeypatch.setattr(batch_prepare,"load_profile",lambda:{})
    monkeypatch.setattr(batch_prepare,"generate_with_llm",lambda *a,**k:(_ for _ in ()).throw(AssertionError("LLM must not run for BASE")))
    raw={"external_id":"greenhouse:base","source":"greenhouse","company_key":"Example Co","title":"Data Engineer",
         "location":"United States","employment_type":"Full-Time","url":"https://example.test/jobs/base",
         "original_url":"https://example.test/jobs/base","ats_provider":"greenhouse","application_route":"EXTERNAL_ATS",
         "tailoring_mode":"BASE_RESUME","resume_strategy":"BASE","description":"Join our team.","description_usable":False,"description_complete":False}
    report=tmp_path/"base.json";out=tmp_path/"manifest.json"
    report.write_text(json.dumps({"results":[{"action":"FINAL_JD_VERIFIED","job":raw,"eligibility":{"experience":{},"sponsorship":{}}}]}),encoding="utf-8")
    rows=batch_prepare.prepare(str(report),str(out))
    assert rows[0]["next_action"]=="READY_TO_APPLY"
    assert rows[0]["ats_audit"]["generation_source"]=="canonical_master_resume_unchanged"
    assert rows[0]["resume_path"] is None
    assert rows[0]["artifact_validation"]["passed"] is True
    assert open(rows[0]["pdf_path"],"rb").read()==master.read_bytes()


def test_base_strategy_fails_closed_when_master_missing(monkeypatch,tmp_path):
    monkeypatch.setattr(batch_prepare,"MASTER_RESUME_PATH",str(tmp_path/"missing.pdf"))
    monkeypatch.setattr(batch_prepare,"load_profile",lambda:{})
    raw={"external_id":"greenhouse:base-missing","source":"greenhouse","company_key":"Example Co","title":"Data Engineer",
         "location":"United States","employment_type":"Full-Time","url":"https://example.test/jobs/base-missing",
         "original_url":"https://example.test/jobs/base-missing","ats_provider":"greenhouse","application_route":"EXTERNAL_ATS",
         "tailoring_mode":"BASE_RESUME","resume_strategy":"BASE","description":"Join our team.","description_complete":False}
    report=tmp_path/"missing.json";out=tmp_path/"manifest.json"
    report.write_text(json.dumps({"results":[{"action":"FINAL_JD_VERIFIED","job":raw,"eligibility":{"experience":{},"sponsorship":{}}}]}),encoding="utf-8")
    rows=batch_prepare.prepare(str(report),str(out))
    assert rows[0]["next_action"]=="HOLD_RESUME_ERROR"
    assert "Canonical master resume PDF is unavailable" in rows[0]["ats_audit"]["error"]


def test_base_strategy_rejects_wrong_master_hash(monkeypatch,tmp_path):
    master=tmp_path/"master.pdf";master.write_bytes(b"%PDF-1.4 wrong-file")
    monkeypatch.setattr(batch_prepare,"MASTER_RESUME_PATH",str(master))
    monkeypatch.setattr(batch_prepare,"MASTER_RESUME_SHA256","0"*64)
    monkeypatch.setattr(batch_prepare,"load_profile",lambda:{})
    raw={"external_id":"greenhouse:wrong-master","source":"greenhouse","company_key":"Example Co","title":"Data Engineer",
         "location":"United States","employment_type":"Full-Time","url":"https://example.test/jobs/wrong",
         "original_url":"https://example.test/jobs/wrong","ats_provider":"greenhouse","application_route":"EXTERNAL_ATS",
         "tailoring_mode":"BASE_RESUME","resume_strategy":"BASE","description":"Join our team.","description_complete":False}
    report=tmp_path/"wrong.json";out=tmp_path/"manifest.json"
    report.write_text(json.dumps({"results":[{"action":"FINAL_JD_VERIFIED","job":raw,"eligibility":{"experience":{},"sponsorship":{}}}]}),encoding="utf-8")
    rows=batch_prepare.prepare(str(report),str(out))
    assert rows[0]["next_action"]=="HOLD_RESUME_ERROR"
    assert "SHA-256 mismatch" in rows[0]["ats_audit"]["error"]


def test_base_strategy_is_idempotent_for_same_job(monkeypatch,tmp_path):
    master=tmp_path/"master.pdf"; master.write_bytes(b"%PDF-1.4 exact-master-bytes")
    monkeypatch.setattr(batch_prepare,"MASTER_RESUME_PATH",str(master))
    import hashlib
    monkeypatch.setattr(batch_prepare,"MASTER_RESUME_SHA256",hashlib.sha256(master.read_bytes()).hexdigest())
    monkeypatch.setattr(batch_prepare,"FINAL_RESUME_DIR",str(tmp_path/"resumes"))
    monkeypatch.setattr(batch_prepare,"load_profile",lambda:{})
    raw={"external_id":"greenhouse:base-repeat","source":"greenhouse","company_key":"Example Co","title":"Data Engineer","location":"United States","employment_type":"Full-Time","url":"https://example.test/jobs/base-repeat","original_url":"https://example.test/jobs/base-repeat","ats_provider":"greenhouse","application_route":"EXTERNAL_ATS","tailoring_mode":"BASE_RESUME","resume_strategy":"BASE","description":"Join our team.","description_usable":False,"description_complete":False}
    report=tmp_path/"repeat.json"; out=tmp_path/"manifest.json"
    report.write_text(json.dumps({"results":[{"action":"FINAL_JD_VERIFIED","job":raw,"eligibility":{"experience":{},"sponsorship":{}}}]}),encoding="utf-8")
    first=batch_prepare.prepare(str(report),str(out)); second=batch_prepare.prepare(str(report),str(out))
    assert first[0]["next_action"]=="READY_TO_APPLY"
    assert second[0]["next_action"]=="READY_TO_APPLY"
    assert first[0]["pdf_path"]==second[0]["pdf_path"]
    assert open(second[0]["pdf_path"],"rb").read()==master.read_bytes()
