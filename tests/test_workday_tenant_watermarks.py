from app import scheduled_runner


def test_workday_tenant_watermarks_advance_independently(monkeypatch, tmp_path):
    state = {
        "last_successful_scan_at": "2026-09-19T14:00:00-04:00",
        "source_watermarks": {"workday": "2026-09-19T14:00:00-04:00"},
        "source_unit_watermarks": {
            "workday:Adobe": "2026-09-19T14:00:00-04:00",
            "workday:Workday": "2026-09-19T14:00:00-04:00",
        },
    }
    source_path = tmp_path / "sources.json"
    source_path.write_text(
        '{"workday":[{"company":"Adobe","tenant":"adobe"},{"company":"Workday","tenant":"Workday"}]}',
        encoding="utf-8",
    )
    saved = {}

    class FixedDateTime(scheduled_runner.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat("2026-09-19T15:00:00-04:00")

    monkeypatch.setattr(scheduled_runner, "datetime", FixedDateTime)
    monkeypatch.setattr(scheduled_runner, "_load_state", lambda: state.copy())
    monkeypatch.setattr(scheduled_runner, "_save_state", lambda value: saved.update(value))

    def fake_cycle(**kwargs):
        assert kwargs["source_unit_hours"]["workday:Adobe"] > 1
        assert kwargs["source_unit_hours"]["workday:Workday"] > 1
        return {
            "cycle_id": "tenant-watermark-test",
            "application_queue": None,
            "queued_for_application": 0,
            "source_status": {"workday": "ERROR"},
            "source_unit_status": {
                "workday:Adobe": "OK",
                "workday:Workday": "ERROR",
            },
        }

    monkeypatch.setattr(scheduled_runner, "run_cycle", fake_cycle)

    result = scheduled_runner.run_scheduled(
        sources=str(source_path),
        ledger=str(tmp_path / "ledger.json"),
        generate_resumes=False,
        force=True,
    )

    assert result["source_unit_watermarks"]["workday:Adobe"] == "2026-09-19T15:00:00-04:00"
    assert result["source_unit_watermarks"]["workday:Workday"] == "2026-09-19T14:00:00-04:00"
    assert result["source_watermarks"]["workday"] == "2026-09-19T14:00:00-04:00"
