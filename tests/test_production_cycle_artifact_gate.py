from app import production_cycle


def _capture_sync(monkeypatch,tmp_path,row):
    ledger={}
    captured=[]
    monkeypatch.setattr(production_cycle,"load_ledger",lambda path:ledger)
    monkeypatch.setattr(production_cycle,"save_ledger",lambda data,path:None)
    monkeypatch.setattr(production_cycle,"record_seen",lambda job,data,status,**extra:captured.append((status,extra)))
    production_cycle._sync_manifest([row],str(tmp_path/"ledger.json"),"cycle")
    return captured[0]


def test_ready_row_without_pdf_is_held(monkeypatch,tmp_path):
    status,extra=_capture_sync(monkeypatch,tmp_path,{
      "external_id":"x1","source":"lever","company":"Example","title":"Data Engineer",
      "next_action":"READY_TO_APPLY","pdf_path":None,
      "artifact_validation":{"passed":True}
    })
    assert status=="HOLD_ARTIFACT_VALIDATION"
    assert extra.get("queue_item") is None


def test_ready_row_with_failed_validation_is_held(monkeypatch,tmp_path):
    pdf=tmp_path/"resume.pdf";pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    status,extra=_capture_sync(monkeypatch,tmp_path,{
      "external_id":"x2","source":"lever","company":"Example","title":"Data Engineer",
      "next_action":"READY_TO_APPLY","pdf_path":str(pdf),
      "artifact_validation":{"passed":False}
    })
    assert status=="HOLD_ARTIFACT_VALIDATION"
    assert extra.get("queue_item") is None


def test_validated_pdf_can_remain_ready(monkeypatch,tmp_path):
    pdf=tmp_path/"resume.pdf";pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    status,extra=_capture_sync(monkeypatch,tmp_path,{
      "external_id":"x3","source":"lever","company":"Example","title":"Data Engineer",
      "next_action":"READY_TO_APPLY","pdf_path":str(pdf),
      "artifact_validation":{"passed":True}
    })
    assert status=="READY_TO_APPLY"
    assert extra["queue_item"]["status"]=="READY_FOR_ATS_ADAPTER"
