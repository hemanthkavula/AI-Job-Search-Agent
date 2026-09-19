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
        monkeypatch.setattr(scheduled_runner, "datetime", type("Clock", (), {"now": staticmethod(lambda tz=None: now), "fromisoformat": staticmethod(datetime.fromisoformat)}))
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
