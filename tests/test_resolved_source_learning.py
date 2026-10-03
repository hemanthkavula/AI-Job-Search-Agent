from app.source_registry import learn_resolved_source, as_discovery_config

def test_branded_resolver_source_round_trips_without_url_redetection():
    registry={}
    added=learn_resolved_source(
        "phenom","Example Co","https://careers.example.com/global/en/search-results",
        registry,identifier="cdn.phenompeople.com"
    )
    assert added is True
    assert registry["phenom"][0]["company"]=="Example Co"
    cfg=as_discovery_config(registry)
    assert cfg["phenom"][0]["search_url"]=="https://careers.example.com/global/en/search-results"

def test_resolved_workday_source_preserves_host_for_execution():
    registry={}
    assert learn_resolved_source(
        "workday","Example Bank","https://example.wd5.myworkdayjobs.com/en-US/External",
        registry,identifier="example|External"
    )
    cfg=as_discovery_config(registry)
    assert cfg["workday"]==[{"company":"Example Bank","host":"example.wd5.myworkdayjobs.com","tenant":"example","site":"External","locale":"en-US"}]

def test_resolved_icims_source_becomes_executable():
    registry={}
    assert learn_resolved_source(
        "icims","Example Co","https://careers-example.icims.com/jobs/search",
        registry,identifier="example"
    )
    cfg=as_discovery_config(registry)
    assert cfg["icims"][0]["company"]=="Example Co"
    assert cfg["icims"][0]["search_url"]=="https://careers-example.icims.com/jobs/search"


def test_verified_custom_career_site_round_trips_into_discovery_config():
    registry={}
    assert learn_resolved_source("career_site","Example Health","https://examplehealth.com/careers",registry)
    cfg=as_discovery_config(registry)
    assert cfg["career_site"][0]["company"]=="Example Health"
    assert cfg["career_site"][0]["search_url"]=="https://examplehealth.com/careers"
    assert cfg["career_site"][0]["job_url_pattern"]
