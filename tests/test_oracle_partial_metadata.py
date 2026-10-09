from app.sources.oracle import _page_metadata_partial_job


def test_oracle_exact_page_metadata_is_partial(monkeypatch):
    page='''<html><meta property="og:title" content="Senior Analytics Engineer"/>
    <meta property="og:site_name" content="EF / Hult"/>
    <meta property="og:description" content="As a Data Engineer, help maintain the data platform. Work with business partners and engineering teams to build scalable analytics data pipelines using SQL and Python, with strong experience in data modeling, pipeline reliability and engineering practices across different parts of our cloud data environment and integrations for analytics and reporting teams." /></html>'''
    monkeypatch.setattr("app.sources.oracle._get", lambda url,timeout: page)
    row=_page_metadata_partial_job("Unknown", "https://jobs.ef.com/en/sites/ef/job/3515", "3515",20)
    assert row is not None
    assert row["company"]=="EF / Hult"
    assert row["title"]=="Senior Analytics Engineer"
    assert row["description_complete"] is False
    assert row["exact_job_metadata_source"]=="oracle_exact_page_og_partial"


def test_oracle_rejects_generic_site_metadata(monkeypatch):
    monkeypatch.setattr("app.sources.oracle._get", lambda url,timeout: '<meta property="og:title" content="Careers"/><meta property="og:description" content="Welcome to jobs"/>')
    assert _page_metadata_partial_job("Unknown","https://jobs.ef.com/en/sites/ef/job/3515","3515",20) is None
