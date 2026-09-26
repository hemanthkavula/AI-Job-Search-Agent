import json
from pathlib import Path
import pytest
from app.production_acceptance import audit

def test_acceptance_passes_consistent_ready_queue(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("generated/cycles").mkdir(parents=True)
    Path("resume.pdf").write_bytes(b"%PDF")
    queue=[{"external_id":"x1","status":"READY_FOR_ATS_ADAPTER","application_gate":{"passed":True},"resume_path":"resume.pdf","artifact_validation":{"passed":True}}]
    Path("queue.json").write_text(json.dumps(queue))
    summary={"cycle_id":"c1","ready_to_apply":1,"queued_for_application":1,"eligible":1,"manifest_ready_to_apply":1,"prepared":1,"resume_generation_enabled":True,"application_queue":"queue.json"}
    p=Path("generated/cycles/c1_summary.json");p.write_text(json.dumps(summary))
    assert audit(str(p))["passed"] is True

def test_acceptance_rejects_count_mismatch(tmp_path):
    p=tmp_path/"summary.json";p.write_text(json.dumps({"ready_to_apply":1,"queued_for_application":0,"eligible":1,"manifest_ready_to_apply":1}))
    with pytest.raises(SystemExit): audit(str(p))
