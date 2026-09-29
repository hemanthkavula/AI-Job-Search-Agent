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


def test_career_detail_link_preserves_structured_location_and_adjacent_de_title(monkeypatch):
    search_html = '<html><a href="/jobs/DI-9">Open role</a></html>'
    detail_html = """<html><script type="application/ld+json">{
      "@type":"JobPosting",
      "identifier":{"value":"DI-9"},
      "title":"Data Infrastructure Engineer",
      "description":"Build Spark data pipelines, ETL, Kafka and lakehouse infrastructure.",
      "url":"https://careers.example.com/jobs/DI-9",
      "datePosted":"2026-09-29",
      "jobLocation":{"address":{"addressLocality":"Jersey City","addressRegion":"NJ","addressCountry":"US"}}
    }</script></html>"""
    def fake_get(url, *args, **kwargs):
        return detail_html if url.endswith("/jobs/DI-9") else search_html
    monkeypatch.setattr(career_site, "_get", fake_get)
    rows = career_site.fetch_jobs("Example", "https://careers.example.com/search", r"/jobs/")
    assert len(rows) == 1
    assert "Jersey City" in rows[0]["location"]
    assert rows[0]["updated_at"] == "2026-09-29"
    assert rows[0]["posted_on"] == "2026-09-29"
