import json
from app import dashboard


def test_cycle_snapshot_includes_auto_and_manual_ready_without_duplicates(monkeypatch,tmp_path):
    monkeypatch.setattr(dashboard,"CYCLES",tmp_path)
    cycle="20260926T160000Z"
    rows=[
      {"external_id":"lever:1","company":"Example Inc","title":"Data Engineer","location":"US",
       "requisition_id":"REQ-1","next_action":"READY_TO_APPLY"},
      {"external_id":"dice:99","company":"Example Inc","title":"Data Engineer","location":"US",
       "requisition_id":"REQ-1","next_action":"READY_TO_APPLY"},
      {"external_id":"manatal:2","company":"Another Co","title":"Senior Data Engineer","location":"Remote",
       "requisition_id":"REQ-2","next_action":"MANUAL_READY_TO_APPLY"},
      {"external_id":"held:3","company":"Held Co","title":"Data Engineer","next_action":"HOLD_ARTIFACT_VALIDATION"},
    ]
    (tmp_path/f"{cycle}_manifest.json").write_text(json.dumps(rows),encoding="utf-8")
    snapshot=dashboard._cycle_snapshot(cycle)
    assert len(snapshot)==2
    assert {x["next_action"] for x in snapshot}=={"READY_TO_APPLY","MANUAL_READY_TO_APPLY"}
    assert {x["company"] for x in snapshot}=={"Example Inc","Another Co"}


def test_pipeline_runs_exposes_manual_ready_count(monkeypatch,tmp_path):
    monkeypatch.setattr(dashboard,"CYCLES",tmp_path)
    cycle="20260926T160000Z"
    (tmp_path/f"{cycle}_summary.json").write_text(json.dumps({
      "cycle_id":cycle,"ready_to_apply":3,"manual_ready_to_apply":2
    }),encoding="utf-8")
    run=dashboard._pipeline_runs()[0]
    assert run["ready"]==3
    assert run["manual_ready"]==2
