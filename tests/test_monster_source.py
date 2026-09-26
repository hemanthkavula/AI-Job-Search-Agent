import json
from app.sources import monster

def test_monster_extracts_jobposting(monkeypatch):
    search='<a href="/job-openings/data-engineer-new-york-ny--abc">job</a>'
    detail='''<script type="application/ld+json">{"@type":"JobPosting","title":"Data Engineer","datePosted":"2026-09-26T10:00:00Z","employmentType":"FULL_TIME","hiringOrganization":{"name":"Example Co"},"jobLocation":{"address":{"addressLocality":"New York","addressRegion":"NY","addressCountry":"US"}},"description":"''' + ("data engineering "*100) + '''"}</script>'''
    monkeypatch.setattr(monster,"SEARCH_TERMS",("Data Engineer",))
    monkeypatch.setattr(monster,"_get",lambda url: detail if "/job-openings/" in url else search)
    rows=monster.fetch_jobs(max_jobs_per_term=5)
    assert len(rows)==1
    job=rows[0]
    assert job["source"]=="monster"
    assert job["company_key"]=="Example Co"
    assert job["title"]=="Data Engineer"
    assert "New York" in job["location"]
    assert job["description_complete"] is True

def test_monster_deduplicates_same_job(monkeypatch):
    search='<a href="/job-openings/data-engineer-new-york-ny--abc">one</a><a href="/job-openings/data-engineer-new-york-ny--abc">two</a>'
    detail='<script type="application/ld+json">{"@type":"JobPosting","title":"Data Engineer","hiringOrganization":{"name":"Example Co"},"identifier":{"value":"123"},"description":"short"}</script>'
    monkeypatch.setattr(monster,"SEARCH_TERMS",("Data Engineer",))
    monkeypatch.setattr(monster,"_get",lambda url: detail if "/job-openings/" in url else search)
    assert len(monster.fetch_jobs())==1
