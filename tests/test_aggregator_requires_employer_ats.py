import json
from datetime import datetime, timezone
from app import jd_finalizer


def _eligible_job(url, source="career_site"):
    return {
        "external_id": "agg:1",
        "source": source,
        "company_key": "Example Health",
        "title": "Data Engineer",
        "location": "United States",
        "employment_type": "Full-Time",
        "url": url,
        "original_url": url,
        "description": "Responsibilities " + ("build data pipelines with Python and SQL. " * 80),
        "description_complete": True,
    }


def test_linkedin_job_cannot_reach_resume_without_employer_ats(monkeypatch, tmp_path):
    report = tmp_path / "eligible.json"
    output = tmp_path / "finalized.json"
    job = _eligible_job("https://www.linkedin.com/jobs/view/123456")
    report.write_text(json.dumps({"results": [{"action": "ELIGIBLE_FOR_RESUME", "job": job}]}), encoding="utf-8")
    monkeypatch.setattr(jd_finalizer, "load_profile", lambda: {})
    monkeypatch.setattr(jd_finalizer, "resolve_full_jd", lambda j: j)
    monkeypatch.setattr(jd_finalizer, "_live_public_job_page", lambda url: (_ for _ in ()).throw(AssertionError("aggregator URL must be held before live validation")))
    result = jd_finalizer.finalize_report(str(report), str(output))
    assert result["finalized"] == 0
    assert result["held_or_rejected"] == 1
    assert result["rejections"][0]["action"] == "HOLD_ATS_UNRESOLVED"


def test_resolved_aggregator_job_can_use_verified_external_ats(monkeypatch, tmp_path):
    report = tmp_path / "eligible.json"
    output = tmp_path / "finalized.json"
    job = _eligible_job("https://boards.greenhouse.io/example/jobs/123456")
    job.update({
        "aggregator_url": "https://www.linkedin.com/jobs/view/123456",
        "ats_provider": "greenhouse",
        "ats_resolution": "employer_career_page_canonical",
    })
    report.write_text(json.dumps({"results": [{"action": "ELIGIBLE_FOR_RESUME", "job": job}]}), encoding="utf-8")
    monkeypatch.setattr(jd_finalizer, "load_profile", lambda: {})
    monkeypatch.setattr(jd_finalizer, "resolve_full_jd", lambda j: j)
    monkeypatch.setattr(jd_finalizer, "_fetch_public_page", lambda url: '<script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-09-27T12:00:00+00:00","jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Jersey City","addressRegion":"NJ","addressCountry":"US"}}}</script>')
    monkeypatch.setattr(jd_finalizer, "_live_public_job_page", lambda url: (True, "reachable"))
    monkeypatch.setattr(jd_finalizer, "two_category_filter", lambda j, p: {"eligible": True})
    monkeypatch.setattr(jd_finalizer, "passes_hard_filters", lambda j, p: (True, []))
    result = jd_finalizer.finalize_report(str(report), str(output), now=datetime(2026,9,28,11,0,tzinfo=timezone.utc))
    assert result["finalized"] == 1
    assert result["results"][0]["job"]["application_route"] == "EXTERNAL_ATS"
