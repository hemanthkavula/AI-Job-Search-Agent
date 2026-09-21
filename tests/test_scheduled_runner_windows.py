from datetime import datetime

from app.scheduled_runner import ET, _window_for


def _dt(year, month, day, hour):
    return datetime(year, month, day, hour, 0, 0, tzinfo=ET)


def test_monday_morning_catches_weekend_from_friday_close():
    now=_dt(2026,9,21,7)  # Monday
    hours,mode,cutoff=_window_for(now,{"last_successful_scan_at":_dt(2026,9,18,19).isoformat()})
    assert mode=="bootstrap"
    assert cutoff==_dt(2026,9,18,19)
    assert hours==60


def test_tuesday_morning_starts_at_monday_close():
    now=_dt(2026,9,22,7)
    hours,mode,cutoff=_window_for(now,{"last_successful_scan_at":_dt(2026,9,21,19).isoformat()})
    assert mode=="bootstrap"
    assert cutoff==_dt(2026,9,21,19)
    assert hours==12


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


def test_missed_previous_close_resumes_from_last_success():
    now=_dt(2026,9,22,7)  # Tuesday
    hours,mode,cutoff=_window_for(now,{"last_successful_scan_at":_dt(2026,9,21,17).isoformat()})
    assert mode=="bootstrap"
    assert cutoff==_dt(2026,9,21,17)
    assert hours==14


def test_missed_friday_close_is_not_lost_over_weekend():
    now=_dt(2026,9,21,7)  # Monday
    hours,mode,cutoff=_window_for(now,{"last_successful_scan_at":_dt(2026,9,18,17).isoformat()})
    assert mode=="bootstrap"
    assert cutoff==_dt(2026,9,18,17)
    assert hours==62


def test_dst_weekend_uses_friday_19_eastern_wall_clock():
    # Monday after the November 2026 DST transition.
    now=_dt(2026,11,2,7)
    hours,mode,cutoff=_window_for(now,{})
    assert mode=="bootstrap"
    assert cutoff.hour==19
    assert cutoff.date().isoformat()=="2026-10-30"
    assert cutoff.utcoffset()!=now.replace(day=30,month=10,hour=19).utcoffset() or cutoff.hour==19
