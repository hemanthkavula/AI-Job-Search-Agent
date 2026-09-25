from app.sources import career_site

def test_schema_jobposting_metadata_and_dedupe():
    body = """<html><script type="application/ld+json">{
      "@context":"https://schema.org","@type":"JobPosting",
      "title":"Senior Data Engineer","description":"Build data engineering pipelines",
      "identifier":{"value":"REQ-123"},"url":"https://example.com/jobs/123?src=test",
      "datePosted":"2026-09-20","validThrough":"2099-10-01T00:00:00Z",
      "employmentType":"FULL_TIME","jobLocationType":"TELECOMMUTE",
      "applicantLocationRequirements":{"@type":"Country","name":"United States"},
      "hiringOrganization":{"@type":"Organization","name":"Example Inc"},
      "skills":"Python, SQL, Spark","experienceRequirements":"5+ years"
    }</script></html>"""
    rows = career_site._jobpostings(body)
    assert len(rows) == 1
    job = rows[0]
    assert career_site._identifier(job, "") == "REQ-123"
    assert career_site._direct_apply_url(job, "").endswith("/jobs/123")
    assert career_site._remote_flag(job) is True
    assert "United States" in career_site._location(job)
    assert career_site._job_type(job) == "FULL_TIME"
    assert career_site._organization(job) == "Example Inc"
    assert career_site._skills(job) == ["Python", "SQL", "Spark"]
    assert career_site._education_experience(job)["experience_requirements"] == "5+ years"
    assert career_site._freshness(job) == "active_by_schema"

def test_dedupe_prefers_stable_job_id():
    rows=[
      {"job_id":"REQ-1","url":"https://example.com/jobs/1"},
      {"job_id":"REQ-1","url":"https://example.com/jobs/1?source=x"},
      {"job_id":"REQ-2","url":"https://example.com/jobs/2"},
    ]
    out=career_site._dedupe_jobs(rows)
    assert [x["job_id"] for x in out] == ["REQ-1","REQ-2"]
