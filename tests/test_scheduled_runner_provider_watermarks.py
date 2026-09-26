from datetime import datetime
from app import scheduled_runner


def test_long_tail_provider_gets_independent_watermark(monkeypatch,tmp_path):
    monkeypatch.setattr(scheduled_runner,"STATE_PATH",tmp_path/"scheduler_state.json")
    monkeypatch.setattr(scheduled_runner,"ROOT",tmp_path)
    (tmp_path/"sources.json").write_text('{"manatal":[{"company":"Example Staffing","search_url":"https://example.test/jobs"}]}',encoding="utf-8")
    class FixedDateTime(datetime):
        @classmethod
        def now(cls,tz=None):
            return cls(2026,9,25,9,7,tzinfo=tz)
    monkeypatch.setattr(scheduled_runner,"datetime",FixedDateTime)
    captured={}
    def fake_cycle(**kwargs):
        captured.update(kwargs)
        return {"cycle_id":"test","source_status":{"manatal":"OK"},"source_errors":{}}
    monkeypatch.setattr(scheduled_runner,"run_cycle",fake_cycle)
    report=scheduled_runner.run_scheduled("sources.json",generate_resumes=False,force=True)
    assert "manatal" in captured["source_hours"]
    assert "manatal" in captured["source_since"]
    assert report["source_watermarks"]["manatal"]==report["scheduler_local_time"]
