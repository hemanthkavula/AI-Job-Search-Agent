from datetime import datetime
from app.scheduled_runner import ET, _window_for


def _dt(year, month, day, hour):
    return datetime(year, month, day, hour, tzinfo=ET)


def test_monday_morning_uses_friday_6pm_checkpoint():
    now=_dt(2026,9,21,7)
    state={"last_successful_discovery_at":_dt(2026,9,18,18).isoformat()}
    hours,mode,start=_window_for(now,state)
    assert hours == 61
    assert mode == "checkpoint"
    assert start == _dt(2026,9,18,18)


def test_tuesday_morning_uses_monday_6pm_checkpoint():
    now=_dt(2026,9,22,7)
    state={"last_successful_discovery_at":_dt(2026,9,21,18).isoformat()}
    hours,mode,start=_window_for(now,state)
    assert hours == 13
    assert mode == "checkpoint"
    assert start == _dt(2026,9,21,18)


def test_hourly_run_uses_previous_successful_hour():
    now=_dt(2026,9,22,8)
    state={"last_successful_discovery_at":_dt(2026,9,22,7).isoformat()}
    hours,mode,start=_window_for(now,state)
    assert hours == 1
    assert mode == "checkpoint"
    assert start == _dt(2026,9,22,7)


def test_missed_run_catches_up_from_last_successful_checkpoint():
    now=_dt(2026,9,22,11)
    state={"last_successful_discovery_at":_dt(2026,9,22,9).isoformat()}
    hours,mode,start=_window_for(now,state)
    assert hours == 2
    assert mode == "checkpoint"
    assert start == _dt(2026,9,22,9)


def test_first_run_monday_has_weekend_fallback():
    now=_dt(2026,9,21,7)
    hours,mode,start=_window_for(now,{})
    assert hours == 61
    assert mode == "weekend_bootstrap"
    assert start == _dt(2026,9,18,18)
