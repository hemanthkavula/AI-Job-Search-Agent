from app.source_registry import detect_ats, _reusable_search_url, as_discovery_config

CASES=[
("https://acme.teamtailor.com/jobs/123-data-engineer","teamtailor"),
("https://acme.recruitee.com/o/data-engineer","recruitee"),
("https://acme.bamboohr.com/careers/42","bamboohr"),
("https://acme.breezy.hr/p/abc-data-engineer","breezyhr"),
("https://ats.rippling.com/acme/jobs/123","rippling"),
("https://acme.pinpointhq.com/postings/123","pinpoint"),
("https://acme.careerplug.com/jobs/123","careerplug"),
("https://acme.freshteam.com/jobs/ABC","freshteam"),
("https://acme.jobs.personio.com/job/123","personio"),
("https://www.comeet.com/jobs/acme/ABC","comeet"),
("https://acme.applicantpro.com/jobs/123","applicantpro"),
("https://www.governmentjobs.com/careers/acme/jobs/123/data-engineer","neogov"),
]

def test_detect_promoted_public_ats_variants():
    for url,expected in CASES:
        provider,identifier=detect_ats(url)
        assert provider == expected, (url,provider,identifier)
        assert identifier

def test_reusable_urls_drop_detail_paths_for_common_boards():
    assert _reusable_search_url("teamtailor","https://acme.teamtailor.com/jobs/123-data-engineer") == "https://acme.teamtailor.com/jobs"
    assert _reusable_search_url("bamboohr","https://acme.bamboohr.com/careers/42") == "https://acme.bamboohr.com/careers"
    assert _reusable_search_url("rippling","https://ats.rippling.com/acme/jobs/123") == "https://ats.rippling.com/acme/jobs"

def test_registry_rows_become_executable_search_urls():
    registry={"teamtailor":[{"company":"Acme","identifier":"acme","original_url":"https://acme.teamtailor.com/jobs/123-data-engineer"}]}
    cfg=as_discovery_config(registry)
    assert cfg["teamtailor"][0]["company"] == "Acme"
    assert cfg["teamtailor"][0]["search_url"] == "https://acme.teamtailor.com/jobs"
