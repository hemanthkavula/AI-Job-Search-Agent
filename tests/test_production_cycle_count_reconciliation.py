from app import production_cycle


def test_summary_ready_count_matches_final_queue(monkeypatch,tmp_path):
    monkeypatch.setattr(production_cycle,"ROOT",tmp_path)
    discovery={"discovered":4,"eligible":3,"source_status":{},"source_errors":{},"source_unit_status":{}}
    finalized={"finalized":3,"held_or_rejected":0,"results":[
      {"action":"FINAL_JD_VERIFIED","job":{"external_id":"1"}},
      {"action":"FINAL_JD_VERIFIED","job":{"external_id":"2"}},
      {"action":"FINAL_JD_VERIFIED","job":{"external_id":"3"}},
    ]}
    manifest=[
      {"external_id":"1","next_action":"READY_TO_APPLY"},
      {"external_id":"2","next_action":"READY_TO_APPLY"},
      {"external_id":"3","next_action":"READY_TO_APPLY"},
    ]
    # Simulate the final queue removing one duplicate/stale row after manifest prep.
    queue=[
      {"external_id":"1","status":"READY_FOR_ATS_ADAPTER"},
      {"external_id":"2","status":"READY_FOR_ATS_ADAPTER"},
    ]
    monkeypatch.setattr(production_cycle,"discover_and_filter",lambda *a,**k:discovery)
    monkeypatch.setattr(production_cycle,"finalize_report",lambda *a,**k:finalized)
    monkeypatch.setattr(production_cycle,"_sync_finalized",lambda *a,**k:None)
    monkeypatch.setattr(production_cycle,"_retry_items_from_ledger",lambda *a,**k:[])
    monkeypatch.setattr(production_cycle,"prepare",lambda *a,**k:manifest)
    monkeypatch.setattr(production_cycle,"_sync_manifest",lambda *a,**k:None)
    monkeypatch.setattr(production_cycle,"build_application_queue",lambda *a,**k:queue)
    summary=production_cycle.run_cycle(generate_resumes=True)
    assert summary["manifest_ready_to_apply"]==3
    assert summary["ready_to_apply"]==2
    assert summary["eligible"]==2
    assert summary["queued_for_application"]==2
    assert "manual_ready_to_apply" not in summary
