import json
from app import daily_runner


def test_long_tail_provider_is_visible_in_production_status(monkeypatch,tmp_path):
    sources=tmp_path/"sources.json"
    sources.write_text(json.dumps({
        "manatal":[{"company":"Example Staffing","search_url":"https://example.careers-page.com/jobs"}],
        "dice":{"enabled":False},
        "ziprecruiter":{"enabled":False}
    }),encoding="utf-8")
    monkeypatch.setattr(daily_runner,"load_profile",lambda:{})
    monkeypatch.setattr(daily_runner,"load_ledger",lambda path:{})
    monkeypatch.setattr(daily_runner,"save_ledger",lambda *a,**k:None)
    monkeypatch.setattr(daily_runner,"load_company_registry",lambda:{})
    monkeypatch.setattr(daily_runner,"save_company_registry",lambda *a,**k:None)
    monkeypatch.setattr(daily_runner,"learn_companies_from_jobs",lambda jobs,reg:reg)
    monkeypatch.setattr(daily_runner,"discover",lambda *a,**k:([],[]))
    report=daily_runner.run(str(sources),ledger_path=str(tmp_path/"ledger.json"))
    assert report["source_status"]["manatal"]=="OK"
