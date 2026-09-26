import json
from app import application_queue


def test_queue_excludes_manual_ready_and_deduplicates_auto_ready(monkeypatch,tmp_path):
    pdf=tmp_path/"resume.pdf";pdf.write_bytes(b"%PDF-test")
    base={"external_id":"lever:1","source":"lever","company":"Example Inc","title":"Data Engineer",
          "location":"United States","employment_type":"Full-Time","description":"Python SQL data engineering",
          "url":"https://jobs.lever.co/example/1","original_url":"https://jobs.lever.co/example/1",
          "ats_provider":"lever","application_route":"EXTERNAL_ATS","pdf_path":str(pdf),
          "artifact_validation":{"passed":True}}
    duplicate=dict(base)
    manual=dict(base,external_id="manatal:2",source="manatal",ats_provider="manatal",
                application_route="MANUAL_VERIFIED_ATS",next_action="MANUAL_READY_TO_APPLY")
    auto=dict(base,next_action="READY_TO_APPLY")
    manifest=tmp_path/"manifest.json";out=tmp_path/"queue.json"
    manifest.write_text(json.dumps([auto,duplicate|{"next_action":"READY_TO_APPLY"},manual]),encoding="utf-8")
    monkeypatch.setattr(application_queue,"load_profile",lambda:{})
    monkeypatch.setattr(application_queue,"_application_gate",lambda row,profile:(True,[]))
    queue=application_queue.build(str(manifest),str(out))
    assert len(queue)==1
    assert queue[0]["external_id"]=="lever:1"
    assert queue[0]["status"]=="READY_FOR_ATS_ADAPTER"
