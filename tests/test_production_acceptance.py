import json
from pathlib import Path
import pytest
from app.production_acceptance import audit

def test_acceptance_passes_consistent_ready_queue(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("generated/cycles").mkdir(parents=True)
    Path("resume.pdf").write_bytes(b"%PDF-1.7\\n")
    queue=[{"external_id":"x1","status":"READY_FOR_ATS_ADAPTER","application_gate":{"passed":True},"resume_path":"resume.pdf","artifact_validation":{"passed":True},"url":"https://jobs.example.com/job/1"}]
    Path("queue.json").write_text(json.dumps(queue))
    summary={"cycle_id":"c1","ready_to_apply":1,"queued_for_application":1,"eligible":1,"manifest_ready_to_apply":1,"prepared":1,"resume_generation_enabled":True,"application_queue":"queue.json"}
    p=Path("generated/cycles/c1_summary.json");p.write_text(json.dumps(summary))
    assert audit(str(p))["passed"] is True

def test_acceptance_rejects_count_mismatch(tmp_path):
    p=tmp_path/"summary.json";p.write_text(json.dumps({"ready_to_apply":1,"queued_for_application":0,"eligible":1,"manifest_ready_to_apply":1}))
    with pytest.raises(SystemExit): audit(str(p))


def test_acceptance_rejects_aggregator_ready_destination(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("resume.pdf").write_bytes(b"%PDF-1.7\\n")
    queue=[{"external_id":"x1","status":"READY_FOR_ATS_ADAPTER","application_gate":{"passed":True},"resume_path":"resume.pdf","artifact_validation":{"passed":True},"url":"https://www.wellfound.com/jobs/1"}]
    Path("queue.json").write_text(json.dumps(queue))
    summary={"cycle_id":"c1","ready_to_apply":1,"queued_for_application":1,"eligible":1,"manifest_ready_to_apply":1,"prepared":1,"resume_generation_enabled":True,"application_queue":"queue.json"}
    p=Path("summary.json");p.write_text(json.dumps(summary))
    with pytest.raises(SystemExit): audit(str(p))

def test_acceptance_rejects_nonexistent_resume_pdf(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    queue=[{"external_id":"x1","status":"READY_FOR_ATS_ADAPTER","application_gate":{"passed":True},"resume_path":"missing.pdf","artifact_validation":{"passed":True},"url":"https://jobs.example.com/job/1"}]
    Path("queue.json").write_text(json.dumps(queue))
    summary={"cycle_id":"c1","ready_to_apply":1,"queued_for_application":1,"eligible":1,"manifest_ready_to_apply":1,"prepared":1,"resume_generation_enabled":True,"application_queue":"queue.json"}
    p=Path("summary.json");p.write_text(json.dumps(summary))
    with pytest.raises(SystemExit): audit(str(p))


def test_acceptance_rejects_cross_provider_duplicate_identity(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("r1.pdf").write_bytes(b"%PDF-1.7\\n")
    Path("r2.pdf").write_bytes(b"%PDF-1.7\\n")
    base={"company":"Example Inc","title":"Senior Data Engineer","location":"United States","requisition_id":"REQ-42","status":"READY_FOR_ATS_ADAPTER","application_gate":{"passed":True},"artifact_validation":{"passed":True}}
    queue=[
      dict(base,external_id="greenhouse:42",source="greenhouse",url="https://boards.greenhouse.io/example/jobs/42",resume_path="r1.pdf"),
      dict(base,external_id="dice:abc",source="dice",url="https://jobs.example.com/req-42",resume_path="r2.pdf"),
    ]
    Path("queue.json").write_text(json.dumps(queue))
    summary={"cycle_id":"c1","ready_to_apply":2,"queued_for_application":2,"eligible":2,"manifest_ready_to_apply":2,"prepared":2,"resume_generation_enabled":True,"application_queue":"queue.json"}
    p=Path("summary.json");p.write_text(json.dumps(summary))
    with pytest.raises(SystemExit,match="duplicate queue job identity"):
        audit(str(p))


def test_acceptance_rejects_renamed_non_pdf_payload(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("resume.pdf").write_bytes(b"not-a-pdf")
    queue=[{"external_id":"x1","status":"READY_FOR_ATS_ADAPTER","application_gate":{"passed":True},"resume_path":"resume.pdf","artifact_validation":{"passed":True},"url":"https://jobs.example.com/job/1"}]
    Path("queue.json").write_text(json.dumps(queue))
    summary={"cycle_id":"c1","ready_to_apply":1,"queued_for_application":1,"eligible":1,"manifest_ready_to_apply":1,"prepared":1,"resume_generation_enabled":True,"application_queue":"queue.json"}
    p=Path("summary.json");p.write_text(json.dumps(summary))
    with pytest.raises(SystemExit,match="invalid PDF signature"):
        audit(str(p))
