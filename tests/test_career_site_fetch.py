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


def test_amazon_search_paginates_and_extracts_data_engineer(monkeypatch):
    page0='<a href="/en/jobs/10561032/data-engineer-partner-experience">Data Engineer</a>'
    detail='<script type="application/ld+json">{"@type":"JobPosting","title":"Data Engineer, Partner Experience","description":"Build scalable data engineering pipelines","identifier":{"value":"10561032"},"datePosted":"2026-09-27","jobLocation":{"address":{"addressLocality":"Seattle","addressRegion":"WA","addressCountry":"US"}}}</script>'
    def fake_get(url, timeout=20):
        if "/en/jobs/10561032/" in url:
            return detail
        if "offset=0" in url:
            return page0
        return ""
    monkeypatch.setattr(career_site, "_get", fake_get)
    jobs=career_site.fetch_jobs("Amazon","https://www.amazon.jobs/en/search?base_query=data+engineer&loc_query=United+States",r"amazon\\.jobs/(?:en/)?jobs/",timeout=1)
    assert [j["job_id"] for j in jobs]==["10561032"]
    assert jobs[0]["ats_provider"]=="amazon_jobs"
    assert jobs[0]["date_posted"]=="2026-09-27"
