import json
from datetime import datetime
from app import scheduled_runner


def test_partial_cycle_does_not_claim_global_success(monkeypatch,tmp_path):
    monkeypatch.setattr(scheduled_runner,"STATE_PATH",tmp_path/"scheduler_state.json")
    monkeypatch.setattr(scheduled_runner,"ROOT",tmp_path)
    (tmp_path/"sources.json").write_text("{}",encoding="utf-8")
    previous="2026-09-25T07:00:00-04:00"
    (tmp_path/"scheduler_state.json").write_text(json.dumps({"last_successful_scan_at":previous}),encoding="utf-8")
    class FixedDateTime(datetime):
        @classmethod
        def now(cls,tz=None):
            return cls(2026,9,25,9,7,tzinfo=tz)
    monkeypatch.setattr(scheduled_runner,"datetime",FixedDateTime)
    monkeypatch.setattr(scheduled_runner,"run_cycle",lambda **kwargs:{
        "cycle_id":"test","source_status":{"greenhouse":"OK","lever":"ERROR"},"source_errors":{"lever":[{"error":"timeout"}]}
    })
    report=scheduled_runner.run_scheduled("sources.json",generate_resumes=False,force=True)
    state=json.loads((tmp_path/"scheduler_state.json").read_text(encoding="utf-8"))
    assert report["cycle_status"]=="PARTIAL"
    assert report["failed_providers"]==["lever"]
    assert state["last_cycle_status"]=="PARTIAL"
    assert state["last_successful_scan_at"]==previous
    assert state["source_watermarks"]["greenhouse"]==report["scheduler_local_time"]
    assert state["source_watermarks"]["lever"]!=report["scheduler_local_time"]


def test_guard_accepted_slot_survives_setup_delay(monkeypatch,tmp_path):
    monkeypatch.setattr(scheduled_runner,"STATE_PATH",tmp_path/"scheduler_state.json")
    monkeypatch.setattr(scheduled_runner,"ROOT",tmp_path)
    (tmp_path/"sources.json").write_text("{}",encoding="utf-8")
    (tmp_path/"scheduler_state.json").write_text(json.dumps({"last_successful_scan_at":"2026-09-28T07:52:00-04:00","last_completed_slot":"2026-09-28T07:30"}),encoding="utf-8")
    class FixedDateTime(datetime):
        @classmethod
        def now(cls,tz=None):
            return cls(2026,9,28,10,57,tzinfo=tz)
    monkeypatch.setattr(scheduled_runner,"datetime",FixedDateTime)
    monkeypatch.setattr(scheduled_runner,"run_cycle",lambda **kwargs:{"cycle_id":"ten-am","source_status":{},"source_errors":{}})
    report=scheduled_runner.run_scheduled("sources.json",generate_resumes=False,accepted_slot="2026-09-28T10:00")
    state=json.loads((tmp_path/"scheduler_state.json").read_text(encoding="utf-8"))
    assert report["cycle_id"]=="ten-am"
    assert report["scheduler_local_time"].startswith("2026-09-28T10:57")
    assert state["last_completed_slot"]=="2026-09-28T10:00"
