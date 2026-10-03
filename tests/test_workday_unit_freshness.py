import json

import app.daily_runner as daily_runner
import app.scheduled_runner as scheduled_runner


def test_workday_rows_are_grouped_by_exact_tenant_cutoff():
    rows=[
        {"source":"workday","company_key":"Company A","external_id":"a"},
        {"source":"workday","company_key":"Company B","external_id":"b"},
    ]
    provider_cutoff="2026-10-02T21:00:00-04:00"
    unit_since={
        "workday:Company A":"2026-10-03T10:00:00-04:00",
        "workday:Company B":"2026-10-02T21:00:00-04:00",
    }
    groups=daily_runner._freshness_groups("workday",rows,provider_cutoff,unit_since)
    assert list(groups["2026-10-03T10:00:00-04:00"])[0]["company_key"] == "Company A"
    assert list(groups["2026-10-02T21:00:00-04:00"])[0]["company_key"] == "Company B"


def test_non_workday_rows_keep_provider_cutoff_even_if_unit_map_has_similar_key():
    rows=[{"source":"greenhouse","company_key":"Company A","external_id":"g"}]
    provider_cutoff="2026-10-03T12:30:00-04:00"
    groups=daily_runner._freshness_groups(
        "greenhouse",rows,provider_cutoff,{"greenhouse:Company A":"2026-10-01T00:00:00-04:00"}
    )
    assert list(groups) == [provider_cutoff]


def test_daily_runner_stamps_workday_jobs_with_tenant_specific_cutoffs(monkeypatch,tmp_path):
    config=tmp_path/"sources.json"
    config.write_text(json.dumps({"workday":[
        {"company":"Company A","host":"a.wd1.myworkdayjobs.com","tenant":"a","site":"jobs"},
        {"company":"Company B","host":"b.wd1.myworkdayjobs.com","tenant":"b","site":"jobs"},
    ]}),encoding="utf-8")
    jobs=[
        {"external_id":"workday:a:jobs:1","source":"workday","company_key":"Company A","title":"Data Engineer","location":"New York, NY","employment_type":"Full-Time","url":"https://a.example/job/1","description":"Build data pipelines with Python SQL Spark Snowflake."},
        {"external_id":"workday:b:jobs:2","source":"workday","company_key":"Company B","title":"Data Engineer","location":"Dallas, TX","employment_type":"Full-Time","url":"https://b.example/job/2","description":"Build data pipelines with Python SQL Spark Snowflake."},
    ]
    monkeypatch.setattr(daily_runner,"load_profile",lambda:{})
    monkeypatch.setattr(daily_runner,"load_ledger",lambda path:{})
    monkeypatch.setattr(daily_runner,"save_ledger",lambda *args,**kwargs:None)
    monkeypatch.setattr(daily_runner,"load_company_registry",lambda:{})
    monkeypatch.setattr(daily_runner,"learn_companies_from_jobs",lambda *args,**kwargs:None)
    monkeypatch.setattr(daily_runner,"save_company_registry",lambda *args,**kwargs:None)
    monkeypatch.setattr(daily_runner,"discover",lambda *args,**kwargs:(jobs,[],{"configured_units_by_provider":{"workday":2}}))
    monkeypatch.setattr(daily_runner,"seen_or_submitted",lambda *args,**kwargs:(False,None,None))
    monkeypatch.setattr(daily_runner,"record_seen",lambda *args,**kwargs:None)
    monkeypatch.setattr(daily_runner,"two_category_filter",lambda *args,**kwargs:{"eligible":True,"sponsorship":{"category":"SPONSORSHIP_NOT_STATED"}})
    monkeypatch.setattr(daily_runner,"passes_hard_filters",lambda *args,**kwargs:(True,[]))
    monkeypatch.setattr(daily_runner,"_current_health_rows",lambda start:[
        {"source":"workday","company":"Company A","status":"OK"},
        {"source":"workday","company":"Company B","status":"OK"},
    ])
    calls=[]
    def fake_fresh(rows,hours,since=None,now=None):
        calls.append((since,[row["company_key"] for row in rows]))
        return rows,[],[]
    monkeypatch.setattr(daily_runner,"fresh_jobs",fake_fresh)

    provider_cutoff="2026-10-02T21:00:00-04:00"
    unit_since={
        "workday:Company A":"2026-10-03T10:00:00-04:00",
        "workday:Company B":"2026-10-02T21:00:00-04:00",
    }
    result=daily_runner.run(
        str(config),hours=20,ledger_path=str(tmp_path/"ledger.json"),
        source_since={"workday":provider_cutoff},source_unit_since=unit_since,
    )
    assert sorted(calls) == sorted([
        (unit_since["workday:Company A"],["Company A"]),
        (unit_since["workday:Company B"],["Company B"]),
    ])
    by_company={row["job"]["company_key"]:row["job"] for row in result["results"]}
    assert by_company["Company A"]["freshness_cutoff"] == unit_since["workday:Company A"]
    assert by_company["Company B"]["freshness_cutoff"] == unit_since["workday:Company B"]


def test_scheduler_passes_exact_workday_unit_since_to_cycle(monkeypatch,tmp_path):
    config=tmp_path/"sources.json"
    config.write_text(json.dumps({"workday":[
        {"company":"Company A","host":"a.wd1.myworkdayjobs.com","tenant":"a","site":"jobs"},
        {"company":"Company B","host":"b.wd1.myworkdayjobs.com","tenant":"b","site":"jobs"},
    ]}),encoding="utf-8")
    state_path=tmp_path/"scheduler_state.json"
    state_path.write_text(json.dumps({
        "last_run_at":"2026-10-03T12:30:00-04:00",
        "source_watermarks":{"workday":"2026-10-02T21:00:00-04:00"},
        "source_unit_watermarks":{
            "workday:Company A":"2026-10-03T10:00:00-04:00",
            "workday:Company B":"2026-10-02T21:00:00-04:00",
        },
    }),encoding="utf-8")
    monkeypatch.setattr(scheduled_runner,"ROOT",tmp_path)
    monkeypatch.setattr(scheduled_runner,"STATE_PATH",state_path)
    monkeypatch.setattr(scheduled_runner,"load_registry",lambda:{})
    monkeypatch.setattr(scheduled_runner,"as_discovery_config",lambda registry:{})
    captured={}
    def fake_cycle(**kwargs):
        captured.update(kwargs)
        return {
            "cycle_id":"unit-cutoff-test",
            "source_status":{"workday":"OK"},
            "source_errors":{},
            "source_unit_status":{"workday:Company A":"OK","workday:Company B":"OK"},
        }
    monkeypatch.setattr(scheduled_runner,"run_cycle",fake_cycle)

    scheduled_runner.run_scheduled("sources.json",str(tmp_path/"ledger.json"),generate_resumes=False,force=True)
    assert captured["source_unit_since"] == {
        "workday:Company A":"2026-10-03T10:00:00-04:00",
        "workday:Company B":"2026-10-02T21:00:00-04:00",
    }
    assert set(captured["source_unit_hours"]) == {"workday:Company A","workday:Company B"}
