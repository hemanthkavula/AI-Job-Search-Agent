from app.source_registry import detect_ats, _reusable_search_url, as_discovery_config

CASES=[
("https://recruitingbypaycor.com/career/CareerHome.action?clientId=abc","paycor"),
("https://hibob-fa0ad69d0cb34a.careers.hibob.com/jobs/123","hibob"),
("https://careers.kula.ai/alaffia/123","kula"),
("https://www.careers-page.com/inclusioncloud","manatal"),
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
("https://acme.eightfold.ai/careers/job/123","eightfold"),
("https://jobs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/Acme/job/123","oracle"),
("https://acme.clearcompany.com/careers/jobs/123","clearcompany"),
("https://apply.fountain.com/acme/opening/123","fountain"),
("https://jobs.zohorecruit.com/recruit/Portal.na?digest=abc","zoho_recruit"),
("https://join.com/companies/acme/123-data-engineer","join"),
("https://jobs.gem.com/acme/123","gem"),
("https://jobs.polymer.co/acme/123","polymer"),
("https://jobs.deel.com/acme/123","deel"),
("https://jobs.ceipal.com/acme/123","ceipal"),
("https://apply.talentreef.com/acme/jobs/123","talentreef"),
("https://jobs.myworkchoice.com/acme/123","myworkchoice"),
("https://secure7.saashr.com/ta/6148957.careers?ShowJob=638026758&lang=en-US","saashr"),
("https://cgi.njoyn.com/corp/xweb/xweb.asp?clid=21001&page=jobdetails&jobid=J0926-1634","njoyn"),
("https://recruitcrm.io/apply/17906227606230064013FlD","recruitcrm"),
("https://www.paycomonline.net/v4/ats/web.php/portal/3223DB71F7BE5AF066B37A016B13E1C1/jobs/102716","paycom"),
("https://recruit.hirebridge.com/v3/Jobs/JobDetails.aspx?cid=6875&jid=609468","hirebridge"),
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


def test_registry_patterns_do_not_contain_accidental_double_regex_escapes():
    from app.source_registry import PATTERNS
    bad=[]
    for provider,patterns in PATTERNS.items():
        for pattern in patterns:
            if r"\\." in pattern or r"\\d" in pattern:
                bad.append((provider,pattern))
    assert not bad, bad


def test_generic_career_path_is_not_misclassified_as_phenom():
    provider,identifier=detect_ats("https://careers.example.com/en/jobs")
    assert provider != "phenom"


def test_localized_rippling_detail_becomes_reusable_tenant_board():
    from app.source_registry import _reusable_search_url
    url="https://ats.rippling.com/es-ES/example-company/jobs/ae82e363-1b4d-4254-9ca1-075ff6ee43e4"
    assert _reusable_search_url("rippling",url)=="https://ats.rippling.com/example-company/jobs"


def test_adp_detail_url_becomes_tenant_board():
    url="https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid=1eb23985-07bc-4029-abf7-ea825bdd7416&ccId=19000101_000001&jobId=23020&lang=en_US"
    reusable=_reusable_search_url("adp_workforce_now",url)
    assert "cid=1eb23985-07bc-4029-abf7-ea825bdd7416" in reusable
    assert "ccId=19000101_000001" in reusable
    assert "jobId=" not in reusable

def test_taleo_detail_url_becomes_career_section_search():
    url="https://cognizant.taleo.net/careersection/lateral/jobdetail.ftl?job=00070744381&lang=en"
    reusable=_reusable_search_url("taleo",url)
    assert reusable=="https://cognizant.taleo.net/careersection/lateral/search.ftl?lang=en"
    assert "00070744381" not in reusable


def test_paycor_detail_becomes_reusable_client_board():
    url="https://recruitingbypaycor.com/career/JobIntroduction.action?clientId=abc&id=job123&source=&lang=en"
    reusable=_reusable_search_url("paycor",url)
    assert "clientId=abc" in reusable
    assert "lang=en" in reusable
    assert "id=" not in reusable
