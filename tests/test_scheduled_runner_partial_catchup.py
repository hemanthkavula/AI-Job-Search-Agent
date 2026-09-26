import json
from datetime import datetime
from app import scheduled_runner


def test_after_partial_cycle_only_failed_provider_catches_up(monkeypatch,tmp_path):
    monkeypatch.setattr(scheduled_runner,"STATE_PATH",tmp_path/"scheduler_state.json")
    monkeypatch.setattr(scheduled_runner,"ROOT",tmp_path)
    (tmp_path/"sources.json").write_text("{}",encoding="utf-8")
    state={
      "last_successful_scan_at":"2026-09-25T07:00:00-04:00",
      "source_watermarks":{
        "greenhouse":"2026-09-25T09:07:00-04:00",
        "lever":"2026-09-25T07:00:00-04:00"
      }
    }
    (tmp_path/"scheduler_state.json").write_text(json.dumps(state),encoding="utf-8")
    class FixedDateTime(datetime):
        @classmethod
        def now(cls,tz=None):
            return cls(2026,9,25,11,7,tzinfo=tz)
    monkeypatch.setattr(scheduled_runner,"datetime",FixedDateTime)
    captured={}
    def fake_cycle(**kwargs):
        captured.update(kwargs)
        return {"cycle_id":"test","source_status":{"greenhouse":"OK","lever":"OK"},"source_errors":{}}
    monkeypatch.setattr(scheduled_runner,"run_cycle",fake_cycle)
    scheduled_runner.run_scheduled("sources.json",generate_resumes=False,force=True)
    assert captured["source_since"]["greenhouse"].startswith("2026-09-25T09:07:00")
    assert captured["source_since"]["lever"].startswith("2026-09-25T07:00:00")
    assert captured["source_hours"]["lever"] > captured["source_hours"]["greenhouse"] + 1.5
