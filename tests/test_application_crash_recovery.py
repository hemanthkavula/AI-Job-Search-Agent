from __future__ import annotations

import json

import pytest

from app.job_identity import canonical_job_key
from app.job_ledger import seen_or_submitted
from app.scheduled_runner import _retry_application_items


def _job():
    return {
        "external_id": "job-123",
        "source": "test",
        "company": "Example",
        "title": "Data Engineer",
        "url": "https://example.invalid/job-123",
    }


def _queue_item():
    return {
        "external_id": "job-123",
        "source": "test",
        "company": "Example",
        "title": "Data Engineer",
        "url": "https://example.invalid/job-123",
        "resume_path": "generated/resumes/example/resume.docx",
        "status": "READY_FOR_ATS_ADAPTER",
    }


def _ledger(status, *, payload=True):
    row = {
        "application_status": status,
        "external_ids": ["job-123"],
        "source": "test",
        "company": "Example",
        "company_key": "Example",
        "title": "Data Engineer",
        "url": "https://example.invalid/job-123",
    }
    if payload:
        row["retry_application"] = _queue_item()
    key = canonical_job_key(_job())
    return {"jobs": {key: row}, "aliases": {alias: key for alias in [key]}}


@pytest.mark.parametrize(
    "status",
    ["READY_TO_APPLY", "IN_PROGRESS", "APPLICATION_IN_PROGRESS", "RETRY_APPLICATION"],
)
def test_interrupted_application_states_are_not_terminal(status):
    assert seen_or_submitted(_job(), _ledger(status))[0] is False


@pytest.mark.parametrize(
    "status",
    ["SUBMITTED", "SUBMITTED_CONFIRMED", "SECURITY_BLOCKED", "MANUAL_ACTION_REQUIRED", "PERMANENT_SKIP"],
)
def test_terminal_application_states_are_not_replayed(status):
    assert seen_or_submitted(_job(), _ledger(status))[0] is True


@pytest.mark.parametrize(
    "status",
    ["READY_TO_APPLY", "IN_PROGRESS", "APPLICATION_IN_PROGRESS", "RETRY_APPLICATION"],
)
def test_interrupted_application_states_replay_persisted_queue_item(tmp_path, status):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(_ledger(status)), encoding="utf-8")

    rows = _retry_application_items(path)

    assert rows == [_queue_item()]


@pytest.mark.parametrize(
    "status",
    ["SUBMITTED", "SUBMITTED_CONFIRMED", "SECURITY_BLOCKED", "MANUAL_ACTION_REQUIRED", "PERMANENT_SKIP"],
)
def test_terminal_application_states_never_replay(tmp_path, status):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(_ledger(status)), encoding="utf-8")

    assert _retry_application_items(path) == []


@pytest.mark.parametrize(
    "bad_payload",
    [
        None,
        {},
        {"external_id": "job-123"},
        {"resume_path": "generated/resumes/example/resume.docx"},
    ],
)
def test_replay_requires_complete_persisted_application_payload(tmp_path, bad_payload):
    ledger = _ledger("RETRY_APPLICATION", payload=False)
    if bad_payload is not None:
        key = canonical_job_key(_job())
        ledger["jobs"][key]["retry_application"] = bad_payload
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(ledger), encoding="utf-8")

    assert _retry_application_items(path) == []
