from app.company_registry import upsert
from app.source_registry import detect_ats

def test_company_registry_is_open_ended():
    reg={}
    upsert(reg,"Previously Unknown Employer",official_domain="example.com",discovered_by="test")
    assert "previously unknown employer" in reg
    assert reg["previously unknown employer"]["official_domain"]=="example.com"

def test_detects_major_official_ats_links():
    cases=[
        ("https://jobs.lever.co/example/123","lever"),
        ("https://boards.greenhouse.io/example/jobs/123","greenhouse"),
        ("https://jobs.ashbyhq.com/example/123","ashby"),
        ("https://example.wd5.myworkdayjobs.com/en-US/External/job/x","workday"),
        ("https://jobs.jobvite.com/example/job/abc","jobvite"),
        ("https://example.icims.com/jobs/123/job","icims"),
        ("https://example.avature.net/en_US/careers/JobDetail/x/1","avature"),
        ("https://apply.workable.com/example/j/ABC","workable"),
    ]
    for url,provider in cases:
        assert detect_ats(url)[0]==provider

def test_unknown_normal_company_site_is_not_falsely_ats():
    assert detect_ats("https://www.example.com/careers")== (None,None)
