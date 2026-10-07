import json
from pathlib import Path
import pytest
from app.production_acceptance import audit

def test_acceptance_passes_consistent_ready_queue(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("generated/cycles").mkdir(parents=True)
    Path("resume.pdf").write_bytes(b"%PDF")
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
    Path("resume.pdf").write_bytes(b"%PDF")
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


def test_strict_acceptance_verifies_freshness_live_and_hard_filters(tmp_path,monkeypatch):
    import app.production_acceptance as production_acceptance
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(production_acceptance,"load_profile",lambda:{
        "candidate_experience_years":5,
        "preferences":{"min_required_years":4,"max_required_years":6},
        "work_authorization":{"requires_sponsorship_future":True},
    })
    Path("resume.pdf").write_bytes(b"%PDF")
    cutoff="2026-10-07T12:00:00+00:00"
    queue=[{
        "external_id":"x1","source":"workday","company":"Example Co",
        "title":"Senior Data Engineer","location":"New York, NY",
        "employment_type":"Full time",
        "description":"Requires 5+ years building Python SQL Spark data pipelines ETL data warehouse data integration systems.",
        "status":"READY_FOR_ATS_ADAPTER","application_gate":{"passed":True},
        "resume_path":"resume.pdf","artifact_validation":{"passed":True},
        "url":"https://example.wd1.myworkdayjobs.com/en-US/jobs/job/x1",
        "freshness_proof":{
            "posted_at":"2026-10-07T13:00:00+00:00",
            "production_cutoff":cutoff,
            "checked_at":"2026-10-07T14:00:00+00:00",
            "basis":"official_employer_posting_date",
        },
        "live_check":{"passed":True,"reason":"reachable"},
        "known_answers":{"requires_future_sponsorship":"Yes"},
    }]
    Path("queue.json").write_text(json.dumps(queue))
    summary={
        "cycle_id":"c1","production_cutoff":cutoff,
        "ready_to_apply":1,"queued_for_application":1,"eligible":1,
        "manifest_ready_to_apply":1,"prepared":1,"resume_generation_enabled":True,
        "application_queue":"queue.json",
    }
    p=Path("summary.json");p.write_text(json.dumps(summary))
    result=production_acceptance.audit(str(p))
    assert result["passed"] is True
    assert result["job_checks"][0]["passed"] is True


def test_strict_acceptance_rejects_stale_freshness_proof(tmp_path,monkeypatch):
    import app.production_acceptance as production_acceptance
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(production_acceptance,"load_profile",lambda:{
        "candidate_experience_years":5,
        "preferences":{"min_required_years":4,"max_required_years":6},
        "work_authorization":{"requires_sponsorship_future":True},
    })
    Path("resume.pdf").write_bytes(b"%PDF")
    cutoff="2026-10-07T12:00:00+00:00"
    queue=[{
        "external_id":"x1","source":"workday","company":"Example Co",
        "title":"Senior Data Engineer","location":"New York, NY","employment_type":"Full time",
        "description":"Requires 5+ years building Python SQL Spark data pipelines ETL data warehouse data integration systems.",
        "status":"READY_FOR_ATS_ADAPTER","application_gate":{"passed":True},
        "resume_path":"resume.pdf","artifact_validation":{"passed":True},
        "url":"https://example.wd1.myworkdayjobs.com/en-US/jobs/job/x1",
        "freshness_proof":{
            "posted_at":"2026-10-06T12:00:00+00:00",
            "production_cutoff":cutoff,
            "checked_at":"2026-10-07T14:00:00+00:00",
            "basis":"official_employer_posting_date",
        },
        "live_check":{"passed":True},
        "known_answers":{"requires_future_sponsorship":"Yes"},
    }]
    Path("queue.json").write_text(json.dumps(queue))
    p=Path("summary.json")
    p.write_text(json.dumps({
        "cycle_id":"c1","production_cutoff":cutoff,
        "ready_to_apply":1,"queued_for_application":1,"eligible":1,
        "manifest_ready_to_apply":1,"prepared":1,"resume_generation_enabled":True,
        "application_queue":"queue.json",
    }))
    with pytest.raises(SystemExit):
        production_acceptance.audit(str(p))
