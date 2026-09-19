from datetime import datetime

from app.scheduled_runner import ET, _window_for


def _dt(year, month, day, hour):
    return datetime(year, month, day, hour, 0, 0, tzinfo=ET)


def test_monday_morning_catches_weekend_from_friday_close():
    now=_dt(2026,9,21,7)  # Monday
    hours,mode,cutoff=_window_for(now,{"last_successful_scan_at":_dt(2026,9,18,18).isoformat()})
    assert mode=="bootstrap"
    assert cutoff==_dt(2026,9,18,18)
    assert hours==61


def test_tuesday_morning_starts_at_monday_close():
    now=_dt(2026,9,22,7)
    hours,mode,cutoff=_window_for(now,{"last_successful_scan_at":_dt(2026,9,21,18).isoformat()})
    assert mode=="bootstrap"
    assert cutoff==_dt(2026,9,21,18)
    assert hours==13


def test_hourly_run_uses_last_successful_scan():
    now=_dt(2026,9,22,8)
    hours,mode,cutoff=_window_for(now,{"last_successful_scan_at":_dt(2026,9,22,7).isoformat()})
    assert mode=="incremental"
    assert cutoff==_dt(2026,9,22,7)
    assert hours==1


def test_missed_hour_is_caught_up():
    now=_dt(2026,9,22,10)
    hours,mode,cutoff=_window_for(now,{"last_successful_scan_at":_dt(2026,9,22,8).isoformat()})
    assert mode=="incremental"
    assert cutoff==_dt(2026,9,22,8)
    assert hours==2


def test_first_run_without_state_uses_previous_close():
    monday=_dt(2026,9,21,7)
    hours,mode,cutoff=_window_for(monday,{})
    assert mode=="bootstrap"
    assert cutoff==_dt(2026,9,18,18)
    assert hours==61

    wednesday=_dt(2026,9,23,7)
    hours,mode,cutoff=_window_for(wednesday,{})
    assert mode=="bootstrap"
    assert cutoff==_dt(2026,9,22,18)
    assert hours==13
