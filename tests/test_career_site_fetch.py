from app.sources import career_site

def test_fetch_jobs_initializes_regex_and_links(monkeypatch):
    search = '<a href="https://example.com/jobs/123">Data Engineer</a>'
    detail = '<script type="application/ld+json">{"@type":"JobPosting","title":"Data Engineer","description":"Build data pipelines","identifier":{"value":"123"},"datePosted":"2026-09-20"}</script>'
    def fake_get(url, timeout=20):
        return search if url == "https://example.com/search" else detail
    monkeypatch.setattr(career_site, "_get", fake_get)
    jobs = career_site.fetch_jobs("Example", "https://example.com/search", r"example\\.com/jobs/", timeout=1)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data Engineer"
