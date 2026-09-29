from app.eligibility import experience_check
from app.sources import career_site


def _profile():
    return {
        "candidate_experience_years": 5,
        "preferences": {"min_required_years": 4, "max_required_years": 7},
    }


def test_experience_window_includes_configured_upper_boundary():
    result = experience_check(
        {"title": "Senior Data Engineer", "description": "Requires 7 years of experience."},
        _profile(),
    )
    assert result["required_years"] == 7
    assert result["eligible"] is True
    assert result["category"] == "EXPERIENCE_ELIGIBLE"


def test_experience_above_configured_upper_boundary_is_rejected():
    result = experience_check(
        {"title": "Senior Data Engineer", "description": "Requires 8 years of experience."},
        _profile(),
    )
    assert result["required_years"] == 8
    assert result["eligible"] is False
    assert result["category"] == "EXPERIENCE_TOO_SENIOR"


def test_career_site_valid_through_never_becomes_posting_freshness(monkeypatch):
    html = """<html><script type="application/ld+json">{
      "@type":"JobPosting",
      "identifier":{"value":"DE-7"},
      "title":"Senior Data Engineer",
      "description":"Build data pipelines with Spark, Kafka, Databricks and ETL.",
      "url":"https://careers.example.com/jobs/DE-7",
      "jobLocation":{"address":{"addressLocality":"New York","addressRegion":"NY","addressCountry":"US"}},
      "employmentType":"FULL_TIME",
      "validThrough":"2099-12-31T23:59:59Z"
    }</script></html>"""
    monkeypatch.setattr(career_site, "_get", lambda *args, **kwargs: html)
    rows = career_site.fetch_jobs(
        "Example",
        "https://careers.example.com/jobs",
        r"/jobs/",
    )
    assert len(rows) == 1
    assert rows[0].get("updated_at") is None
    assert rows[0].get("posted_on") is None
    assert rows[0].get("valid_through") == "2099-12-31T23:59:59Z"
