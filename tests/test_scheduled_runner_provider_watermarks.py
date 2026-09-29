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


def test_structured_workday_unit_status_advances_tenant_watermark(monkeypatch,tmp_path):
    monkeypatch.setattr(scheduled_runner,"STATE_PATH",tmp_path/"scheduler_state.json")
    monkeypatch.setattr(scheduled_runner,"ROOT",tmp_path)
    (tmp_path/"sources.json").write_text('{"workday":[{"company":"Example","host":"example.wd1.myworkdayjobs.com","tenant":"example","site":"External"}]}',encoding="utf-8")
    class FixedDateTime(datetime):
        @classmethod
        def now(cls,tz=None):
            return cls(2026,9,29,10,5,tzinfo=tz)
    monkeypatch.setattr(scheduled_runner,"datetime",FixedDateTime)
    monkeypatch.setattr(scheduled_runner,"load_registry",lambda:{})
    monkeypatch.setattr(scheduled_runner,"as_discovery_config",lambda registry:{"workday":[]})
    def fake_cycle(**kwargs):
        return {"cycle_id":"test","source_status":{"workday":"OK"},"source_errors":{},
                "source_unit_status":{"workday:Example":{"source":"workday","company":"Example","status":"OK","jobs_returned":3}}}
    monkeypatch.setattr(scheduled_runner,"run_cycle",fake_cycle)
    report=scheduled_runner.run_scheduled("sources.json",generate_resumes=False,force=True)
    assert report["source_unit_watermarks"]["workday:Example"]==report["scheduler_local_time"]


def test_next_cycle_uses_exact_prior_success_without_overlap(monkeypatch,tmp_path):
    import json
    monkeypatch.setattr(scheduled_runner,"STATE_PATH",tmp_path/"scheduler_state.json")
    monkeypatch.setattr(scheduled_runner,"ROOT",tmp_path)
    (tmp_path/"sources.json").write_text("{}",encoding="utf-8")
    (tmp_path/"scheduler_state.json").write_text(json.dumps({"last_successful_scan_at":"2026-09-29T07:30:00-04:00","source_watermarks":{"greenhouse":"2026-09-29T07:30:00-04:00"}}),encoding="utf-8")
    class FixedDateTime(datetime):
        @classmethod
        def now(cls,tz=None): return cls(2026,9,29,10,0,tzinfo=tz)
    monkeypatch.setattr(scheduled_runner,"datetime",FixedDateTime)
    captured={}
    def fake_cycle(**kwargs):
        captured.update(kwargs); return {"cycle_id":"exact-window","source_status":{"greenhouse":"OK"},"source_errors":{}}
    monkeypatch.setattr(scheduled_runner,"run_cycle",fake_cycle)
    scheduled_runner.run_scheduled("sources.json",generate_resumes=False,force=True)
    assert captured["since"].startswith("2026-09-29T07:30:00")
    assert captured["source_since"]["greenhouse"].startswith("2026-09-29T07:30:00")
    assert abs(captured["hours"]-2.5)<0.0001
    assert abs(captured["source_hours"]["greenhouse"]-2.5)<0.0001
