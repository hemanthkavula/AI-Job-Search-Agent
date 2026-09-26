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


def test_discovery_portal_applies_freshness_window(monkeypatch):
    fresh='''<script type="application/ld+json">{"@type":"JobPosting","title":"Data Engineer","datePosted":"2099-01-01T00:00:00Z","description":"data engineering sql python","hiringOrganization":{"name":"Fresh Co"},"url":"https://fresh.example/jobs/1"}</script>'''
    old='''<script type="application/ld+json">{"@type":"JobPosting","title":"Data Engineer","datePosted":"2020-01-01T00:00:00Z","description":"data engineering sql python","hiringOrganization":{"name":"Old Co"},"url":"https://old.example/jobs/1"}</script>'''
    monkeypatch.setattr(discovery_portal,"_get",lambda url,timeout=20: fresh+old)
    rows=discovery_portal.fetch_jobs("feed","https://feed.example/jobs",r"/jobs/",hours=24)
    assert [r["company_key"] for r in rows]==["Fresh Co"]
