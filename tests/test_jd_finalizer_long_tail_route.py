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
    monkeypatch.setattr(jd_finalizer,"analyze_job_with_llm",lambda j:None)
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
    monkeypatch.setattr(jd_finalizer,"_official_job_location",lambda page,job:"Jersey City, NJ, US")
    monkeypatch.setattr(jd_finalizer,"_live_public_job_page",lambda url:(True,"reachable"))
    monkeypatch.setattr(jd_finalizer,"two_category_filter",lambda j,p:{"eligible":True})
    monkeypatch.setattr(jd_finalizer,"passes_hard_filters",lambda j,p:(True,[]))
    result=jd_finalizer.finalize_report(str(report),str(output),hours=24,now=datetime(2026,9,28,17,0,tzinfo=timezone.utc))
    assert result["finalized"]==1
    assert result["results"][0]["job"]["freshness_basis"]=="dice_date_fallback_after_official_ats_resolution"


def test_partial_but_usable_jd_is_finalized_for_limited_resume(monkeypatch,tmp_path):
    report=tmp_path/"partial.json"; output=tmp_path/"partial_out.json"
    job={
        "external_id":"greenhouse:partial","source":"greenhouse","company_key":"Example Co",
        "title":"Data Engineer","location":"United States","employment_type":"Full-Time",
        "original_url":"https://boards.greenhouse.io/example/jobs/partial",
        "description":"Responsibilities: build Python SQL Spark pipelines. Requirements: 5+ years data engineering.",
        "description_usable":True,"description_complete":False,"description_length":91,"jd_signal_score":3,
    }
    report.write_text(json.dumps({"results":[{"action":"ELIGIBLE_FOR_RESUME","job":job}]}),encoding="utf-8")
    monkeypatch.setattr(jd_finalizer,"load_profile",lambda:{})
    monkeypatch.setattr(jd_finalizer,"resolve_full_jd",lambda j:j)
    monkeypatch.setattr(jd_finalizer,"_live_public_job_page",lambda url:(True,"reachable"))
    monkeypatch.setattr(jd_finalizer,"two_category_filter",lambda j,p:{"eligible":True})
    monkeypatch.setattr(jd_finalizer,"passes_hard_filters",lambda j,p:(True,[]))
    monkeypatch.setattr(jd_finalizer,"analyze_job_with_llm",lambda j:None)
    result=jd_finalizer.finalize_report(str(report),str(output))
    assert result["finalized"]==1
    assert result["results"][0]["job"]["resume_strategy"]=="LIMITED"
    assert result["results"][0]["job"]["tailoring_mode"]=="LIMITED_JD"
    assert result["results"][0]["job"]["coverage_target_count"]>0


def test_complete_jd_is_finalized_with_full_jd_tailoring_mode(monkeypatch,tmp_path):
    report=tmp_path/"complete.json"; output=tmp_path/"complete_out.json"
    description="Responsibilities: build Python SQL Spark pipelines. Requirements: 5+ years data engineering. Qualifications: cloud data platforms. "+("data engineering pipelines warehouse orchestration. "*35)
    job={
        "external_id":"greenhouse:complete","source":"greenhouse","company_key":"Example Co",
        "title":"Data Engineer","location":"United States","employment_type":"Full-Time",
        "original_url":"https://boards.greenhouse.io/example/jobs/complete",
        "description":description,"description_usable":True,"description_complete":True,
        "description_length":len(description),"jd_signal_score":3,
    }
    report.write_text(json.dumps({"results":[{"action":"ELIGIBLE_FOR_RESUME","job":job}]}),encoding="utf-8")
    monkeypatch.setattr(jd_finalizer,"load_profile",lambda:{})
    monkeypatch.setattr(jd_finalizer,"resolve_full_jd",lambda j:j)
    monkeypatch.setattr(jd_finalizer,"_live_public_job_page",lambda url:(True,"reachable"))
    monkeypatch.setattr(jd_finalizer,"two_category_filter",lambda j,p:{"eligible":True})
    monkeypatch.setattr(jd_finalizer,"passes_hard_filters",lambda j,p:(True,[]))
    monkeypatch.setattr(jd_finalizer,"analyze_job_with_llm",lambda j:None)
    result=jd_finalizer.finalize_report(str(report),str(output))
    assert result["finalized"]==1
    assert result["results"][0]["action"]=="FINAL_JD_VERIFIED"
    assert result["results"][0]["job"]["resume_strategy"]=="FULL"
    assert result["results"][0]["job"]["tailoring_mode"]=="FULL_JD"
