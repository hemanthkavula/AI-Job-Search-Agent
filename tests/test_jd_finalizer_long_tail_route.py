import json
from app import jd_finalizer


def test_verified_long_tail_ats_is_finalized_for_external_handoff(monkeypatch,tmp_path):
    report=tmp_path/"eligible.json"
    output=tmp_path/"finalized.json"
    job={
        "external_id":"manatal:1","source":"manatal","company_key":"Example Staffing",
        "title":"Data Engineer","location":"United States","employment_type":"Full-Time",
        "url":"https://example.careers-page.com/jobs/1","original_url":"https://example.careers-page.com/jobs/1",
        "ats_provider":"manatal","description":"Responsibilities " + ("build data pipelines Python SQL. "*80),
        "description_complete":True,
    }
    report.write_text(json.dumps({"results":[{"action":"ELIGIBLE_FOR_RESUME","job":job}]}),encoding="utf-8")
    monkeypatch.setattr(jd_finalizer,"load_profile",lambda:{})
    monkeypatch.setattr(jd_finalizer,"resolve_full_jd",lambda j:j)
    monkeypatch.setattr(jd_finalizer,"_live_public_job_page",lambda url:(True,"reachable"))
    monkeypatch.setattr(jd_finalizer,"two_category_filter",lambda j,p:{"eligible":True})
    monkeypatch.setattr(jd_finalizer,"passes_hard_filters",lambda j,p:(True,[]))
    result=jd_finalizer.finalize_report(str(report),str(output))
    assert result["finalized"]==1
    raw=result["results"][0]["job"]
    assert raw["application_route"]=="EXTERNAL_ATS"
    assert "manual_application_required" not in raw


def test_dice_date_fallback_only_after_official_ats_resolution(monkeypatch,tmp_path):
    from datetime import datetime, timezone
    report=tmp_path/"eligible_dice.json"; output=tmp_path/"finalized_dice.json"
    job={
        "external_id":"dice:1","source":"dice","company_key":"Example Co",
        "title":"Data Engineer","location":"United States","employment_type":"Full-Time",
        "url":"https://www.dice.com/job-detail/1","original_url":"https://jobs.example.com/data-engineer",
        "aggregator_url":"https://www.dice.com/job-detail/1",
        "ats_resolution":"employer_career_page_canonical","ats_provider":"greenhouse",
        "posted_at":"2026-09-28T15:00:00+00:00",
        "description":"Responsibilities " + ("build data pipelines Python SQL Spark. "*80),
        "description_complete":True,
    }
    report.write_text(json.dumps({"results":[{"action":"ELIGIBLE_FOR_RESUME","job":job}]}),encoding="utf-8")
    monkeypatch.setattr(jd_finalizer,"load_profile",lambda:{})
    monkeypatch.setattr(jd_finalizer,"resolve_full_jd",lambda j:j)
    monkeypatch.setattr(jd_finalizer,"_fetch_public_page",lambda url:"<html><body>Job open, no posted date</body></html>")
    monkeypatch.setattr(jd_finalizer,"_live_public_job_page",lambda url:(True,"reachable"))
    monkeypatch.setattr(jd_finalizer,"two_category_filter",lambda j,p:{"eligible":True})
    monkeypatch.setattr(jd_finalizer,"passes_hard_filters",lambda j,p:(True,[]))
    result=jd_finalizer.finalize_report(str(report),str(output),hours=24,now=datetime(2026,9,28,17,0,tzinfo=timezone.utc))
    assert result["finalized"]==1
    assert result["results"][0]["job"]["freshness_basis"]=="dice_date_fallback_official_date_unavailable"