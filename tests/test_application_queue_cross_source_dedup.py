import json
from app import application_queue


def test_final_queue_blocks_same_requisition_with_different_external_ids(monkeypatch,tmp_path):
    pdf=tmp_path/"resume.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    base={
      "next_action":"READY_TO_APPLY","company":"Example Inc","title":"Senior Data Engineer",
      "location":"United States","employment_type":"Full-time","description":"data engineer",
      "requisition_id":"REQ-123","pdf_path":str(pdf),"artifact_validation":{"passed":True},
    }
    rows=[
      dict(base,external_id="dice:abc",source="dice",url="https://dice.example/job/abc",ats_provider="dice"),
      dict(base,external_id="lever:xyz",source="lever",url="https://jobs.lever.co/example/xyz",ats_provider="lever"),
    ]
    manifest=tmp_path/"manifest.json";output=tmp_path/"queue.json"
    manifest.write_text(json.dumps(rows),encoding="utf-8")
    monkeypatch.setattr(application_queue,"load_profile",lambda:{})
    monkeypatch.setattr(application_queue,"_application_gate",lambda row,profile:(True,[]))
    queue=application_queue.build(str(manifest),str(output))
    assert len(queue)==1
    assert queue[0]["external_id"]=="dice:abc"
