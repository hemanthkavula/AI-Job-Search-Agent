from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# A partial provider failure must not make the global window grow forever.
# Per-provider watermarks already preserve catch-up for the failed source.
replace_once(
    "app/scheduled_runner.py",
    '''def _scheduled_cutoff(now,state):
    """Return the exact lower bound for this scan.

    Normal hourly runs start at the last successful scan. The first run of a
    weekday starts at the previous weekday's 18:00 cutoff; Monday therefore
    catches Friday 18:00 through Monday morning. If a daytime run was missed,
    the next run catches up from the last successful scan instead of losing jobs.
    """
    last=_parse_state_time(state.get("last_successful_scan_at"))
    today=now.date()
    # Construct the prior scheduled close as a local wall-clock time instead of
    # subtracting elapsed hours. This preserves 19:00 Eastern across DST changes.
    days_back=3 if now.weekday()==0 else 1
    prior_date=today-timedelta(days=days_back)
    prior_close=datetime(prior_date.year,prior_date.month,prior_date.day,FINAL_HOUR,tzinfo=ET)
    if last is None:return prior_close,"bootstrap"
    # The persisted watermark is authoritative. If the prior 18:00 run was
    # missed (for example the last success was 17:00), resume at 17:00 so no
    # posting interval is silently lost.
    if last.date()!=today:return last,"bootstrap"
    return last,"incremental"
''',
    '''def _scheduled_cutoff(now,state):
    """Return the global lower bound while preserving source-specific catch-up.

    The global window advances from the most recent attempted cycle, even when
    one provider failed. Failed providers do not lose coverage: each provider
    and Workday tenant has its own watermark and therefore independently catches
    up from its last successful discovery. This prevents one persistently failing
    provider from stretching every later cycle/finalizer window for days.

    Older scheduler state that lacks ``last_run_at`` safely falls back to the
    legacy successful watermark. A brand-new state still bootstraps from the
    previous weekday close so weekend/missed-run coverage is retained.
    """
    last_attempt=_parse_state_time(state.get("last_run_at"))
    last_success=_parse_state_time(state.get("last_successful_scan_at"))
    last=last_attempt or last_success
    today=now.date()
    # Construct the prior scheduled close as a local wall-clock time instead of
    # subtracting elapsed hours so DST transitions preserve the requested clock.
    days_back=3 if now.weekday()==0 else 1
    prior_date=today-timedelta(days=days_back)
    prior_close=datetime(prior_date.year,prior_date.month,prior_date.day,FINAL_HOUR,tzinfo=ET)
    if last is None:return prior_close,"bootstrap"
    if last.date()!=today:return last,"bootstrap"
    return last,"incremental"
''',
)

# Final freshness validation must use the exact cutoff stamped on each job by
# its source-specific discovery pass, not the scheduler's broad fallback window.
replace_once(
    "app/jd_finalizer.py",
    '''    out["jd_resolution_source"]="employer_career_page_canonical" if employer_url and should_resolve_employer else ("employer_career_page_fallback" if employer_url else ("jsonld_or_original_ats_public_job_detail_page" if len(resolved)>len(current) else "source_payload"))
    return out

def finalize_report(report_path,output_path="generated/finalized_jobs.json",hours=24,now=None):
''',
    '''    out["jd_resolution_source"]="employer_career_page_canonical" if employer_url and should_resolve_employer else ("employer_career_page_fallback" if employer_url else ("jsonld_or_original_ats_public_job_detail_page" if len(resolved)>len(current) else "source_payload"))
    return out

def _job_freshness_cutoff(job,fallback):
    value=(job or {}).get("freshness_cutoff")
    if value in (None,""):
        return fallback
    try:
        parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if parsed.tzinfo is None:
            parsed=parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError,ValueError):
        return fallback

def finalize_report(report_path,output_path="generated/finalized_jobs.json",hours=24,now=None):
''',
)
replace_once(
    "app/jd_finalizer.py",
    '''        check_now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cutoff=check_now-timedelta(hours=hours)
''',
    '''        check_now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        global_cutoff=check_now-timedelta(hours=hours)
        cutoff=_job_freshness_cutoff(raw,global_cutoff)
''',
)
replace_once(
    "app/jd_finalizer.py",
    '''            held.append({"job":raw,"action":"REJECT_STALE_OFFICIAL_POSTING","reason":"Official employer/ATS posting date is outside the requested freshness window; discovery/repost/refresh dates were ignored.","diagnostics":{"url":application_url,"official_posted_at":official_posted.isoformat(),"official_posted_label":official_label,"freshness_hours":hours,"discovery_source":raw.get("source")}})
''',
    '''            held.append({"job":raw,"action":"REJECT_STALE_OFFICIAL_POSTING","reason":"Official employer/ATS posting date is outside the source-specific freshness window; discovery/repost/refresh dates were ignored.","diagnostics":{"url":application_url,"official_posted_at":official_posted.isoformat(),"official_posted_label":official_label,"freshness_cutoff":cutoff.isoformat(),"global_freshness_hours":hours,"discovery_source":raw.get("source")}})
''',
)

# Regression: a partial cycle advances the global window from the attempt, while
# failed providers continue to use their independent older source watermark.
p = Path("tests/test_scheduled_runner_windows.py")
text = p.read_text(encoding="utf-8")
text += '''

def test_partial_cycle_uses_last_attempt_for_global_window():
    now=_dt(2026,9,22,11)
    state={
        "last_successful_scan_at":_dt(2026,9,22,7).isoformat(),
        "last_run_at":_dt(2026,9,22,9).isoformat(),
        "last_cycle_status":"PARTIAL",
        "last_failed_providers":["discovery_portal"],
    }
    hours,mode,cutoff=_window_for(now,state)
    assert mode=="incremental"
    assert cutoff==_dt(2026,9,22,9)
    assert hours==2


def test_legacy_state_without_last_run_still_uses_success_watermark():
    now=_dt(2026,9,22,11)
    hours,mode,cutoff=_window_for(now,{"last_successful_scan_at":_dt(2026,9,22,7).isoformat()})
    assert mode=="incremental"
    assert cutoff==_dt(2026,9,22,7)
    assert hours==4
'''
p.write_text(text, encoding="utf-8")

# Regression: a broad global catch-up window must not allow a job older than the
# source cutoff that admitted it during discovery.
p = Path("tests/test_updated_at_fallback_finalizer.py")
text = p.read_text(encoding="utf-8")
text += '''

def test_finalizer_uses_job_source_freshness_cutoff_not_broad_global_window(tmp_path, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(finalizer,"_fetch_public_page",lambda url:'<html><script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-10-03T09:00:00Z"}</script></html>')
    monkeypatch.setattr(finalizer,"_live_public_job_page",lambda url:(True,"reachable"))
    monkeypatch.setattr(finalizer,"two_category_filter",lambda job,profile:{"eligible":True})
    monkeypatch.setattr(finalizer,"passes_hard_filters",lambda job,profile:(True,[]))
    report_path=_report(tmp_path)
    payload=json.loads(report_path.read_text(encoding="utf-8"))
    payload["results"][0]["job"]["freshness_cutoff"]="2026-10-03T10:00:00Z"
    report_path.write_text(json.dumps(payload),encoding="utf-8")
    result=finalizer.finalize_report(
        report_path,output_path=tmp_path/"final_source_cutoff.json",hours=183,
        now=datetime(2026,10,3,13,0,tzinfo=timezone.utc),
    )
    assert result["finalized"]==0
    assert result["rejections"][0]["action"]=="REJECT_STALE_OFFICIAL_POSTING"
    assert result["rejections"][0]["diagnostics"]["freshness_cutoff"]=="2026-10-03T10:00:00+00:00"
'''
p.write_text(text, encoding="utf-8")

print("Applied source-specific freshness-window fix")
