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
