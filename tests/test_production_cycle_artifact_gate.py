from app import production_cycle


def _capture_sync(monkeypatch,tmp_path,row):
    ledger={}
    captured=[]
    monkeypatch.setattr(production_cycle,"load_ledger",lambda path:ledger)
    monkeypatch.setattr(production_cycle,"save_ledger",lambda data,path:None)
    monkeypatch.setattr(production_cycle,"record_seen",lambda job,data,status,**extra:captured.append((status,extra,job)))
    production_cycle._sync_manifest([row],str(tmp_path/"ledger.json"),"cycle")
    return captured[0]


def test_ready_row_without_pdf_is_held(monkeypatch,tmp_path):
    status,extra,_=_capture_sync(monkeypatch,tmp_path,{
      "external_id":"x1","source":"lever","company":"Example","title":"Data Engineer",
      "next_action":"READY_TO_APPLY","pdf_path":None,
      "artifact_validation":{"passed":True}
    })
    assert status=="HOLD_ARTIFACT_VALIDATION"
    assert extra.get("queue_item") is None


def test_ready_row_with_failed_validation_is_held(monkeypatch,tmp_path):
    pdf=tmp_path/"resume.pdf";pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    status,extra,_=_capture_sync(monkeypatch,tmp_path,{
      "external_id":"x2","source":"lever","company":"Example","title":"Data Engineer",
      "next_action":"READY_TO_APPLY","pdf_path":str(pdf),
      "artifact_validation":{"passed":False}
    })
    assert status=="HOLD_ARTIFACT_VALIDATION"
    assert extra.get("queue_item") is None


def test_validated_pdf_can_remain_ready(monkeypatch,tmp_path):
    pdf=tmp_path/"resume.pdf";pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    status,extra,_=_capture_sync(monkeypatch,tmp_path,{
      "external_id":"x3","source":"lever","company":"Example","title":"Data Engineer",
      "next_action":"READY_TO_APPLY","pdf_path":str(pdf),
      "artifact_validation":{"passed":True}
    })
    assert status=="READY_TO_APPLY"
    assert extra["queue_item"]["status"]=="READY_FOR_ATS_ADAPTER"


def test_manifest_sync_preserves_authoritative_identity_fields(monkeypatch,tmp_path):
    _,_,job=_capture_sync(monkeypatch,tmp_path,{
      "external_id":"x4","source":"smartrecruiters","company":"Example Inc","title":"Senior Data Engineer",
      "location":"Jersey City, NJ","original_url":"https://jobs.smartrecruiters.com/Example/123",
      "url":"https://aggregator.example/jobs/123","requisition_id":"REQ-123",
      "next_action":"PREPARED"
    })
    assert job["location"]=="Jersey City, NJ"
    assert job["original_url"]=="https://jobs.smartrecruiters.com/Example/123"
    assert job["requisition_id"]=="REQ-123"
