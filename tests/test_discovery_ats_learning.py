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


def test_unknown_employer_from_dice_persists_resolved_lever_board(monkeypatch,tmp_path):
    broad={
        "external_id":"dice:unknown-1",
        "source":"dice",
        "company_key":"Previously Unknown Employer",
        "company":"Previously Unknown Employer",
        "title":"Senior Data Engineer",
        "url":"https://www.dice.com/job-detail/unknown-1",
        "description":"Python SQL Spark data pipelines",
    }
    registry_path=tmp_path/"registry.json"
    monkeypatch.setattr(discovery,"dice_jobs",lambda *a,**k:[broad])
    monkeypatch.setattr(discovery,"resolve_original_ats",lambda job:{
        **job,
        "original_url":"https://jobs.lever.co/previouslyunknown/abc",
        "ats_provider":"lever",
        "ats_identifier":"previouslyunknown",
    })
    config={"dice":{"enabled":True},"ziprecruiter":{"enabled":False}}
    rows,errors=discovery.discover(
        config,
        only_source="dice",
        registry_path=registry_path,
        health_path=tmp_path/"health.json",
    )
    assert not errors
    assert len(rows)==1
    assert rows[0]["target_company"] is False
    saved=discovery.load_registry(registry_path)
    assert any(
        x.get("identifier")=="previouslyunknown"
        and x.get("company")=="Previously Unknown Employer"
        for x in saved["lever"]
    )


def test_learned_lever_board_is_executed_on_later_discovery(monkeypatch,tmp_path):
    registry_path=tmp_path/"registry.json"
    discovery.save_registry({
        "lever":[{
            "company":"Learned Employer",
            "identifier":"learned-employer",
            "learned_from":"dice",
            "original_url":"https://jobs.lever.co/learned-employer/abc",
        }]
    },registry_path)
    called=[]
    monkeypatch.setattr(discovery,"lever_jobs",lambda site: called.append(site) or [{
        "external_id":"lever:learned:1",
        "source":"lever",
        "company_key":"Learned Employer",
        "title":"Data Engineer",
        "url":"https://jobs.lever.co/learned-employer/abc",
        "description":"Python SQL ETL",
    }])
    rows,errors=discovery.discover(
        {"lever":[],"dice":{"enabled":False},"ziprecruiter":{"enabled":False}},
        only_source="lever",
        registry_path=registry_path,
        health_path=tmp_path/"health.json",
    )
    assert not errors
    assert called==["learned-employer"]
    assert [x["external_id"] for x in rows]==["lever:learned:1"]
