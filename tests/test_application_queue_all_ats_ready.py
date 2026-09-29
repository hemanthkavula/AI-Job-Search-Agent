import json
from app import application_queue


def test_unknown_or_long_tail_ats_does_not_downgrade_valid_ready_job(monkeypatch,tmp_path):
    pdf=tmp_path/"resume.pdf";pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    rows=[{
      "external_id":"manatal:1","source":"manatal","company":"Example","title":"Data Engineer",
      "location":"United States","employment_type":"Full-time","description":"data engineer",
      "url":"https://example.manatal.com/jobs/1","original_url":"https://example.manatal.com/jobs/1",
      "ats_provider":"manatal","application_route":"MANUAL_VERIFIED_ATS",
      "next_action":"READY_TO_APPLY","pdf_path":str(pdf),"artifact_validation":{"passed":True}
    }]
    manifest=tmp_path/"manifest.json";output=tmp_path/"queue.json"
    manifest.write_text(json.dumps(rows),encoding="utf-8")
    monkeypatch.setattr(application_queue,"load_profile",lambda:{})
    monkeypatch.setattr(application_queue,"_application_gate",lambda row,profile:(True,[]))
    queue=application_queue.build(str(manifest),str(output))
    assert len(queue)==1
    assert queue[0]["status"]=="READY_FOR_ATS_ADAPTER"
    assert queue[0]["status_reason"] is None


def test_queue_rejects_ready_manifest_without_artifact_validation(monkeypatch,tmp_path):
    pdf=tmp_path/"resume.pdf";pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    rows=[{"external_id":"lever:legacy","source":"lever","company":"Example","title":"Data Engineer",
           "location":"United States","employment_type":"Full-time","description":"data engineer",
           "url":"https://jobs.lever.co/example/legacy","original_url":"https://jobs.lever.co/example/legacy",
           "next_action":"READY_TO_APPLY","pdf_path":str(pdf)}]
    manifest=tmp_path/"manifest.json";output=tmp_path/"queue.json"
    manifest.write_text(json.dumps(rows),encoding="utf-8")
    monkeypatch.setattr(application_queue,"load_profile",lambda:{})
    monkeypatch.setattr(application_queue,"_application_gate",lambda row,profile:(True,[]))
    assert application_queue.build(str(manifest),str(output))==[]


def test_queue_rejects_missing_pdf_even_when_validation_says_passed(monkeypatch,tmp_path):
    rows=[{"external_id":"lever:missing","source":"lever","company":"Example","title":"Data Engineer",
           "location":"United States","employment_type":"Full-time","description":"data engineer",
           "url":"https://jobs.lever.co/example/missing","original_url":"https://jobs.lever.co/example/missing",
           "next_action":"READY_TO_APPLY","pdf_path":str(tmp_path/"missing.pdf"),
           "artifact_validation":{"passed":True}}]
    manifest=tmp_path/"manifest.json";output=tmp_path/"queue.json"
    manifest.write_text(json.dumps(rows),encoding="utf-8")
    monkeypatch.setattr(application_queue,"load_profile",lambda:{})
    monkeypatch.setattr(application_queue,"_application_gate",lambda row,profile:(True,[]))
    assert application_queue.build(str(manifest),str(output))==[]
