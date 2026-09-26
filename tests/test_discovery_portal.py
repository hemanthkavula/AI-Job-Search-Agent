import json
from app.sources import discovery_portal

def test_discovery_portal_marks_rows_non_authoritative(monkeypatch):
    page='''<script type="application/ld+json">{"@type":"JobPosting","title":"Senior Data Engineer","datePosted":"2026-09-26T10:00:00Z","employmentType":"FULL_TIME","url":"https://startup.example/jobs/123","hiringOrganization":{"name":"Startup Co"},"jobLocation":{"address":{"addressLocality":"New York","addressRegion":"NY","addressCountry":"US"}},"description":"''' + ("data engineering python sql "*80) + '''"}</script>'''
    monkeypatch.setattr(discovery_portal,"_get",lambda url,timeout=20: page)
    rows=discovery_portal.fetch_jobs("startup_feed","https://feed.example/jobs",r"/jobs/")
    assert len(rows)==1
    job=rows[0]
    assert job["source"]=="startup_feed"
    assert job["discovery_only"] is True
    assert job["authoritative_source"] is False
    assert job["company_key"]=="Startup Co"

def test_discovery_portal_filters_non_data_roles(monkeypatch):
    page='<script type="application/ld+json">{"@type":"JobPosting","title":"Account Executive","description":"sales revenue accounts","hiringOrganization":{"name":"Startup Co"}}</script>'
    monkeypatch.setattr(discovery_portal,"_get",lambda url,timeout=20: page)
    assert discovery_portal.fetch_jobs("startup_feed","https://feed.example/jobs",r"/jobs/")==[]
