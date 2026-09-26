import json

from app import company_universe


def test_authoritative_feeder_official_url_preserves_provenance(monkeypatch,tmp_path):
    sources=tmp_path/"sources.json"
    sources.write_text(json.dumps({"career_site":[]}),encoding="utf-8")
    monkeypatch.setattr(company_universe,"ROOT",tmp_path)
    monkeypatch.setattr(company_universe,"collect_company_feeders",lambda: ([{
        "company":"Private Example Inc",
        "official_url":"https://private-example.test",
        "discovered_by":"verified_private_catalog",
    }],[]))
    monkeypatch.setattr(company_universe,"load_registry",lambda *a,**k:{})
    saved={}
    monkeypatch.setattr(company_universe,"save_registry",lambda reg,*a,**k:saved.update(reg))
    monkeypatch.setattr(company_universe,"load_source_registry",lambda:{})
    monkeypatch.setattr(company_universe,"save_source_registry",lambda reg:None)
    monkeypatch.setattr(company_universe,"resolve_career_page",lambda domain:None)
    result=company_universe.build("sources.json",registry_path=tmp_path/"registry.json",domain_budget=0,career_budget=1)
    row=next(iter(saved.values()))
    assert row["official_domain"]=="private-example.test"
    assert row["domain_evidence"]=="verified_private_catalog"
    assert result["feeder_rows"]==1
