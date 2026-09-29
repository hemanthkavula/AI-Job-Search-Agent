from datetime import datetime

from app import scheduled_runner


def test_failed_provider_keeps_old_watermark(monkeypatch, tmp_path):
    old_state = scheduled_runner.STATE_PATH
    scheduled_runner.STATE_PATH = tmp_path / "state.json"
    try:
        now = datetime(2026, 9, 21, 10, 0, tzinfo=scheduled_runner.ET)
        prior = datetime(2026, 9, 21, 9, 0, tzinfo=scheduled_runner.ET)
        scheduled_runner._save_state({
            "last_successful_scan_at": prior.isoformat(),
            "source_watermarks": {"workday": prior.isoformat(), "dice": prior.isoformat()},
        })
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now
        monkeypatch.setattr(scheduled_runner, "datetime", Clock)
        monkeypatch.setattr(scheduled_runner, "run_cycle", lambda **kwargs: {
            "cycle_id": "test", "application_queue": None, "queued_for_application": 0,
            "source_status": {"workday": "ERROR", "dice": "OK"},
        })

        result = scheduled_runner.run_scheduled(generate_resumes=False, force=True)

        assert result["source_watermarks"]["workday"] == prior.isoformat()
        assert result["source_watermarks"]["dice"] == now.isoformat()
    finally:
        scheduled_runner.STATE_PATH = old_state


def test_source_window_uses_provider_watermark(monkeypatch, tmp_path):
    old_state = scheduled_runner.STATE_PATH
    scheduled_runner.STATE_PATH = tmp_path / "state.json"
    captured = {}
    try:
        now = datetime(2026, 9, 21, 10, 0, tzinfo=scheduled_runner.ET)
        global_prior = datetime(2026, 9, 21, 9, 0, tzinfo=scheduled_runner.ET)
        workday_prior = datetime(2026, 9, 21, 8, 0, tzinfo=scheduled_runner.ET)
        scheduled_runner._save_state({
            "last_successful_scan_at": global_prior.isoformat(),
            "source_watermarks": {"workday": workday_prior.isoformat()},
        })
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now
        monkeypatch.setattr(scheduled_runner, "datetime", Clock)
        def fake_cycle(**kwargs):
            captured.update(kwargs)
            return {"cycle_id": "test", "application_queue": None, "queued_for_application": 0, "source_status": {}}
        monkeypatch.setattr(scheduled_runner, "run_cycle", fake_cycle)

        scheduled_runner.run_scheduled(generate_resumes=False, force=True)

        assert captured["source_since"]["workday"] == workday_prior.isoformat()
        assert captured["source_since"]["dice"] == global_prior.isoformat()
        assert captured["source_hours"]["workday"] > captured["source_hours"]["dice"]
    finally:
        scheduled_runner.STATE_PATH = old_state


def test_structured_provider_status_advances_and_reports_failures(monkeypatch, tmp_path):
    old_state = scheduled_runner.STATE_PATH
    scheduled_runner.STATE_PATH = tmp_path / "state.json"
    try:
        now = datetime(2026, 9, 21, 10, 0, tzinfo=scheduled_runner.ET)
        prior = datetime(2026, 9, 21, 9, 0, tzinfo=scheduled_runner.ET)
        scheduled_runner._save_state({
            "last_successful_scan_at": prior.isoformat(),
            "source_watermarks": {"dice": prior.isoformat(), "ziprecruiter": prior.isoformat()},
        })
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now
        monkeypatch.setattr(scheduled_runner, "datetime", Clock)
        monkeypatch.setattr(scheduled_runner, "run_cycle", lambda **kwargs: {
            "cycle_id": "structured-status", "source_status": {
                "dice": {"status": "OK", "jobs": 5},
                "ziprecruiter": {"status": "ERROR", "error": "upstream"},
            },
        })

        result = scheduled_runner.run_scheduled(generate_resumes=False, force=True)

        assert result["source_watermarks"]["dice"] == now.isoformat()
        assert result["source_watermarks"]["ziprecruiter"] == prior.isoformat()
        assert result["failed_providers"] == ["ziprecruiter"]
        assert result["cycle_status"] == "PARTIAL"
    finally:
        scheduled_runner.STATE_PATH = old_state


def test_partial_provider_keeps_watermark_and_cycle_partial(monkeypatch, tmp_path):
    old_state = scheduled_runner.STATE_PATH
    scheduled_runner.STATE_PATH = tmp_path / "state.json"
    try:
        now = datetime(2026, 9, 21, 10, 0, tzinfo=scheduled_runner.ET)
        prior = datetime(2026, 9, 21, 9, 0, tzinfo=scheduled_runner.ET)
        scheduled_runner._save_state({
            "last_successful_scan_at": prior.isoformat(),
            "source_watermarks": {"eightfold": prior.isoformat()},
        })
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now
        monkeypatch.setattr(scheduled_runner, "datetime", Clock)
        monkeypatch.setattr(scheduled_runner, "run_cycle", lambda **kwargs: {
            "cycle_id": "partial-provider",
            "source_status": {"eightfold": "PARTIAL"},
        })

        result = scheduled_runner.run_scheduled(generate_resumes=False, force=True)

        assert result["source_watermarks"]["eightfold"] == prior.isoformat()
        assert result["failed_providers"] == ["eightfold"]
        assert result["cycle_status"] == "PARTIAL"
        persisted = scheduled_runner._load_state()
        assert persisted["last_successful_scan_at"] == prior.isoformat()
    finally:
        scheduled_runner.STATE_PATH = old_state
