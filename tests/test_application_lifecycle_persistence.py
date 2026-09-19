from __future__ import annotations

import json

from app.job_identity import canonical_job_key
from app.job_ledger import seen_or_submitted
from app.production_cycle import _sync_manifest
from app.scheduled_runner import _retry_application_items


def _manifest_row():
    return {
        "external_id": "job-1",
        "source": "test",
        "company": "Example",
        "title": "Data Engineer",
        "url": "https://example.invalid/job-1",
        "original_url": "https://example.invalid/job-1",
        "ats_provider": "lever",
        "application_route": "EXTERNAL_ATS",
        "pdf_path": "generated/resumes/example.pdf",
        "artifact_validation": {"passed": True},
        "next_action": "READY_TO_APPLY",
    }


def test_ready_to_apply_persists_replay_payload(tmp_path):
    ledger_path = tmp_path / "ledger.json"
    _sync_manifest([_manifest_row()], ledger_path)

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    row = next(iter(ledger["jobs"].values()))

    assert row["application_status"] == "READY_TO_APPLY"
    assert row["queue_item"]["external_id"] == "job-1"
    assert row["queue_item"]["resume_path"].endswith("example.pdf")
    assert _retry_application_items(ledger_path) == [row["queue_item"]]


def test_uncertain_submission_attempt_is_terminal_and_not_replayed(tmp_path):
    job = {
        "external_id": "job-1",
        "source": "test",
        "company": "Example",
        "title": "Data Engineer",
        "url": "https://example.invalid/job-1",
    }
    key = canonical_job_key(job)
    queue_item = {"external_id": "job-1", "resume_path": "generated/resumes/example.pdf"}
    ledger = {
        "jobs": {
            key: {
                "application_status": "SUBMISSION_ATTEMPTED",
                "source": "test",
                "company": "Example",
                "title": "Data Engineer",
                "url": job["url"],
                "external_ids": ["job-1"],
                "retry_application": queue_item,
            }
        },
        "aliases": {key: key},
    }
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

    assert seen_or_submitted(job, ledger)[0] is True
    assert _retry_application_items(ledger_path) == []
