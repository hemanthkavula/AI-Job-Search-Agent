import json
from datetime import datetime, timedelta, timezone

from app import daily_runner, freshness, jd_finalizer


def _walmart_job():
    return {
        "external_id":"workday:walmart:WalmartExternal:R-2560824",
        "source":"workday",
        "company_key":"Walmart",
        "title":"Senior, Data Engineer",
        "location":"Bentonville, AR | Sunnyvale, CA",
        "employment_type":"Full time",
        "url":"https://walmart.wd5.myworkdayjobs.com/en-US/WalmartExternal/job/Bentonville-AR/Senior-Data-Engineer_R-2560824",
        "posted_on":"Posted 2 Days Ago",
        "updated_at":"2026-10-05T12:00:00+00:00",
        "description":"Build enterprise data pipelines with Python SQL Spark ETL data warehouse and data lake systems. Responsibilities and qualifications for data engineering. " + "x"*1300,
        "description_complete":True,
        "description_usable":True,
        "ats_provider":"workday",
    }


def test_old_recovery_job_cannot_enter_current_cycle(tmp_path, monkeypatch):
    now=datetime(2026,10,7,12,0,tzinfo=timezone.utc)
    cutoff=(now-timedelta(hours=10,minutes=39)).isoformat()
    sources=tmp_path/"sources.json"
    sources.write_text("{}",encoding="utf-8")
    monkeypatch.setattr(freshness,"STATE",tmp_path/"seen.json")
    monkeypatch.setattr(freshness,"STATUS",tmp_path/"status.json")
    monkeypatch.setattr(daily_runner,"discover",lambda *a,**k:([_walmart_job()],[],{}))
    monkeypatch.setattr(daily_runner,"load_profile",lambda:{})
    monkeypatch.setattr(daily_runner,"load_ledger",lambda path:{})
    monkeypatch.setattr(daily_runner,"save_ledger",lambda *a,**k:None)
    monkeypatch.setattr(daily_runner,"load_company_registry",lambda:{})
    monkeypatch.setattr(daily_runner,"save_company_registry",lambda *a,**k:None)
    monkeypatch.setattr(daily_runner,"learn_companies_from_jobs",lambda *a,**k:None)

    report=daily_runner.run(
        str(sources),
        hours=10.75,
        ledger_path=str(tmp_path/"ledger.json"),
        since=cutoff,
        scan_now=now,
        # Simulate the Run #283 condition: Workday recovery is much older than
        # the active production cutoff.
        source_since={"workday":"2026-09-18T22:00:00+00:00"},
        source_hours={"workday":445.9},
        source_unit_hours={"workday:Walmart":84.5},
    )

    assert report["discovered"]==1
    assert report["fresh_verified_within_hours"]==0
    assert report["eligible"]==0
    assert report["older_or_unverified"]==1


def test_final_gate_rejects_posted_two_days_ago_against_exact_cutoff(tmp_path, monkeypatch):
    now=datetime(2026,10,7,12,0,tzinfo=timezone.utc)
    cutoff="2026-10-07T01:21:00+00:00"
    report_path=tmp_path/"eligible.json"
    output_path=tmp_path/"finalized.json"
    job=_walmart_job()
    report_path.write_text(json.dumps({
        "results":[{"action":"ELIGIBLE_FOR_RESUME","job":job}]
    }),encoding="utf-8")

    monkeypatch.setattr(jd_finalizer,"resolve_full_jd",lambda j:j)
    monkeypatch.setattr(jd_finalizer,"job_detail_is_live",lambda *a,**k:(True,{}))
    monkeypatch.setattr(jd_finalizer,"load_profile",lambda:{})

    result=jd_finalizer.finalize_report(
        str(report_path),
        str(output_path),
        hours=445.9,
        now=now,
        since=cutoff,
    )

    assert result["finalized"]==0
    assert result["held_or_rejected"]==1
    rejection=result["rejections"][0]
    assert rejection["action"]=="REJECT_STALE_OFFICIAL_POSTING"
    assert rejection["job"]["official_posted_label"]=="Posted 2 Days Ago"
    assert rejection["diagnostics"]["production_cutoff"]==cutoff
