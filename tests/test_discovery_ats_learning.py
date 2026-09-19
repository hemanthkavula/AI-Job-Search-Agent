import app.discovery as discovery


def test_broad_discovery_resolves_ats_before_learning(monkeypatch,tmp_path):
    broad={
        "external_id":"dice:1",
        "source":"dice",
        "company_key":"Example",
        "title":"Data Engineer",
        "url":"https://www.dice.com/job-detail/1",
        "description":"summary",
    }
    monkeypatch.setattr(discovery,"dice_jobs",lambda *a,**k:[broad])
    monkeypatch.setattr(discovery,"resolve_original_ats",lambda job:{
        **job,
        "original_url":"https://jobs.lever.co/example/abc",
        "ats_provider":"lever",
        "ats_identifier":"example",
    })
    learned=[]
    monkeypatch.setattr(discovery,"learn_from_jobs",lambda jobs,registry: learned.extend(jobs) or [])
    monkeypatch.setattr(discovery,"load_registry",lambda path:{})
    config={"dice":{"enabled":True},"ziprecruiter":{"enabled":False}}
    rows,errors=discovery.discover(
        config,
        only_source="dice",
        registry_path=tmp_path/"registry.json",
        health_path=tmp_path/"health.json",
    )
    assert not errors
    assert rows[0]["url"]=="https://www.dice.com/job-detail/1"
    assert learned[0]["original_url"]=="https://jobs.lever.co/example/abc"
