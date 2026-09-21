from datetime import datetime
import json

from app import scheduled_runner


def test_failed_provider_keeps_legacy_global_cutoff_on_migration(monkeypatch, tmp_path):
    state_path = tmp_path / "scheduler_state.json"
    ledger_path = tmp_path / "ledger.json"
    state_path.write_text(json.dumps({
        "last_successful_scan_at": "2026-09-19T09:00:00-04:00"
    }), encoding="utf-8")

    monkeypatch.setattr(scheduled_runner, "STATE_PATH", state_path)
    monkeypatch.setattr(
        scheduled_runner,
        "run_cycle",
        lambda **kwargs: {
            "cycle_id": "test-cycle",
            "application_queue": None,
            "queued_for_application": 0,
            "source_status": {
                "workday": "ERROR",
                "dice": "OK",
            },
        },
    )

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls.fromisoformat("2026-09-19T10:00:00-04:00")
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(scheduled_runner, "datetime", FixedDateTime)

    summary = scheduled_runner.run_scheduled(
        ledger=str(ledger_path),
        generate_resumes=False,
        force=True,
    )

    assert summary["source_watermarks"]["workday"] == "2026-09-19T09:00:00-04:00"
    assert summary["source_watermarks"]["dice"] == "2026-09-19T10:00:00-04:00"

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["source_watermarks"]["workday"] == "2026-09-19T09:00:00-04:00"
    assert saved["source_watermarks"]["dice"] == "2026-09-19T10:00:00-04:00"
