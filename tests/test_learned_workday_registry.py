from app.source_registry import as_discovery_config, learn_from_jobs

def test_learned_workday_board_round_trips_to_discovery_config():
    registry={"greenhouse":[],"lever":[],"ashby":[],"smartrecruiters":[],"workday":[],"icims":[],"jobvite":[]}
    jobs=[{
        "source":"dice",
        "company_key":"Example Co",
        "original_url":"https://example.wd5.myworkdayjobs.com/en-US/External/job/123",
    }]
    added=learn_from_jobs(jobs,registry)
    assert added and added[0]["provider"]=="workday"
    assert registry["workday"][0]["host"]=="example.wd5.myworkdayjobs.com"
    cfg=as_discovery_config(registry)
    assert cfg["workday"]==[{
        "company":"Example Co",
        "host":"example.wd5.myworkdayjobs.com",
        "tenant":"example",
        "site":"External",
        "locale":"en-US",
    }]
