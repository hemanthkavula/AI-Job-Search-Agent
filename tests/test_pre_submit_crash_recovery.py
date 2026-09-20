from __future__ import annotations

import json

import pytest

from app import scheduled_runner


def _queue_item():
    return {
        "external_id": "job-crash-1",
        "source": "test",
        "company": "Example",
        "title": "Data Engineer",
        "location": "Jersey City, NJ, United States",
        "employment_type": "Full-time",
        "description": "Build data pipelines with Python, SQL, Spark, Databricks, ETL and data integration.",
        "url": "https://example.invalid/job-crash-1",
        "resume_path": "generated/resumes/example.pdf",
        "status": "READY_FOR_ATS_ADAPTER",
    }


def test_scheduler_persists_terminal_marker_before_submit_crash(monkeypatch, tmp_path):
    ledger_path = tmp_path / "ledger.json"
    queue_rel = "generated/test_pre_submit_crash_queue.json"
    queue_path = scheduled_runner.ROOT / queue_rel
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps([_queue_item()]), encoding="utf-8")

    monkeypatch.setattr(
        scheduled_runner,
        "run_cycle",
        lambda **kwargs: {
            "cycle_id": "pre-submit-crash-test",
            "application_queue": queue_rel,
            "queued_for_application": 1,
            "source_status": {},
        },
    )
    monkeypatch.setattr(scheduled_runner, "_load_state", lambda: {})
    monkeypatch.setattr(scheduled_runner, "_save_state", lambda state: None)

    def crash_after_durable_marker(**kwargs):
        callback = kwargs["before_submit"]
        item = _queue_item()
        callback(item, {
            "external_id": item["external_id"],
            "url": item["url"],
            "final_submit_action": "Submit application",
            "final_submit_scope_url": item["url"],
        })
        raise RuntimeError("simulated crash immediately before/around final submit click")

    monkeypatch.setattr(scheduled_runner, "run_applications", crash_after_durable_marker)

    with pytest.raises(RuntimeError, match="simulated crash"):
        scheduled_runner.run_scheduled(
            ledger=str(ledger_path),
            generate_resumes=False,
            force=True,
            apply_ready=True,
            allow_submit=True,
        )

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    row = next(iter(ledger["jobs"].values()))
    assert row["application_status"] == "SUBMISSION_ATTEMPTED"
    assert row["submission_attempted"] is True
    assert row["retry_application"] is None
    assert scheduled_runner._retry_application_items(ledger_path) == []

    try:
        queue_path.unlink()
    except OSError:
        pass


def test_pre_submit_gate_blocks_non_us_queue_item(monkeypatch, tmp_path):
    ledger_path = tmp_path / "ledger.json"
    queue_rel = "generated/test_non_us_pre_submit_queue.json"
    queue_path = scheduled_runner.ROOT / queue_rel
    item = _queue_item()
    item["location"] = "Bangalore, India"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps([item]), encoding="utf-8")

    monkeypatch.setattr(
        scheduled_runner,
        "run_cycle",
        lambda **kwargs: {
            "cycle_id": "non-us-pre-submit-test",
            "application_queue": queue_rel,
            "queued_for_application": 1,
            "source_status": {},
        },
    )
    monkeypatch.setattr(scheduled_runner, "_load_state", lambda: {})
    monkeypatch.setattr(scheduled_runner, "_save_state", lambda state: None)

    called = {"applications": False}
    def should_not_run(**kwargs):
        called["applications"] = True
        return []
    monkeypatch.setattr(scheduled_runner, "run_applications", should_not_run)

    summary = scheduled_runner.run_scheduled(
        ledger=str(ledger_path),
        generate_resumes=False,
        force=True,
        apply_ready=True,
        allow_submit=True,
    )

    assert summary["pre_submit_gate_blocked"] == 1
    assert summary["queued_for_application"] == 0
    assert called["applications"] is False
    saved = json.loads(queue_path.read_text(encoding="utf-8"))
    assert saved[0]["status"] == "MANUAL_ACTION_REQUIRED"
    assert "location outside United States target" in saved[0]["status_reason"]

    try:
        queue_path.unlink()
    except OSError:
        pass
