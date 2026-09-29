import json
from app import dashboard


def test_cycle_snapshot_includes_only_ready_jobs_without_duplicates(monkeypatch,tmp_path):
    monkeypatch.setattr(dashboard,"CYCLES",tmp_path)
    cycle="20260926T160000Z"
    rows=[
      {"external_id":"lever:1","company":"Example Inc","title":"Data Engineer","location":"US","requisition_id":"REQ-1","next_action":"READY_TO_APPLY"},
      {"external_id":"dice:99","company":"Example Inc","title":"Data Engineer","location":"US","requisition_id":"REQ-1","next_action":"READY_TO_APPLY"},
      {"external_id":"manatal:2","company":"Another Co","title":"Senior Data Engineer","location":"Remote","requisition_id":"REQ-2","next_action":"READY_TO_APPLY"},
      {"external_id":"manual:3","company":"Manual Co","title":"Data Engineer","location":"US","requisition_id":"REQ-3","next_action":"MANUAL_READY_TO_APPLY"},
      {"external_id":"held:3","company":"Held Co","title":"Data Engineer","next_action":"HOLD_ARTIFACT_VALIDATION"},
    ]
    (tmp_path/f"{cycle}_manifest.json").write_text(json.dumps(rows),encoding="utf-8")
    snapshot=dashboard._cycle_snapshot(cycle)
    assert len(snapshot)==2
    assert all(x["next_action"]=="READY_TO_APPLY" for x in snapshot)
    assert {x["company"] for x in snapshot}=={"Example Inc","Another Co"}


def test_pipeline_runs_exposes_single_ready_count(monkeypatch,tmp_path):
    monkeypatch.setattr(dashboard,"CYCLES",tmp_path)
    cycle="20260926T160000Z"
    (tmp_path/f"{cycle}_summary.json").write_text(json.dumps({"cycle_id":cycle,"ready_to_apply":5}),encoding="utf-8")
    run=dashboard._pipeline_runs()[0]
    assert run["ready"]==5
    assert "manual_ready" not in run


def test_pipeline_jobs_never_matches_different_requisition_by_company_title(monkeypatch,tmp_path):
    cycle="20260929T160000Z"
    cycles=tmp_path/"cycles"; cycles.mkdir()
    state=tmp_path/"state"; state.mkdir()
    monkeypatch.setattr(dashboard,"CYCLES",cycles)
    monkeypatch.setattr(dashboard,"STATE_DIR",state)
    monkeypatch.setattr(dashboard,"LEDGER",state/"job_ledger.json")
    monkeypatch.setattr(dashboard,"HIDDEN",state/"hidden_applications.json")
    snapshot={"external_id":"ats:old","company":"Same Co","title":"Data Engineer","location":"US","requisition_id":"REQ-OLD","next_action":"READY_TO_APPLY"}
    (cycles/f"{cycle}_manifest.json").write_text(json.dumps([snapshot]),encoding="utf-8")
    (state/"job_ledger.json").write_text(json.dumps({"jobs":{"ats:new":{"external_id":"ats:new","company":"Same Co","title":"Data Engineer","location":"US","requisition_id":"REQ-NEW","application_status":"READY_TO_APPLY"}}}),encoding="utf-8")
    rows=dashboard._pipeline_jobs(cycle)
    assert len(rows)==1
    assert rows[0]["key"]=="ats:old"


def test_confirmed_resume_recovery_requires_exact_identity(monkeypatch,tmp_path):
    state=tmp_path/"state"; state.mkdir()
    resumes=state/"resumes"; resumes.mkdir()
    wrong=resumes/"wrong.pdf"; wrong.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(dashboard,"STATE_DIR",state)
    monkeypatch.setattr(dashboard,"LEDGER",state/"job_ledger.json")
    (state/"job_ledger.json").write_text(json.dumps({"jobs":{"new":{"external_id":"ats:new","company":"Same Co","title":"Data Engineer","location":"US","requisition_id":"REQ-NEW","pdf_path":str(wrong)}}}),encoding="utf-8")
    hist={"job_key":"ats:old","external_id":"ats:old","company":"Same Co","title":"Data Engineer","location":"US","requisition_id":"REQ-OLD"}
    assert dashboard._resume_path_from_confirmed(hist) is None
