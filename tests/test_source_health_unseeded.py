import json
from pathlib import Path
from app import source_health

def test_source_health_reports_unseeded_provider(tmp_path, monkeypatch):
    cfg={"greenhouse":[],"talentreef":[],"jobappnetwork":[]}
    p=tmp_path/"sources.json"
    p.write_text(json.dumps(cfg),encoding="utf-8")
    monkeypatch.setattr(source_health,"ROOT",Path(tmp_path))
    report=source_health.run("sources.json",timeout=1)
    by_provider={r["provider"]:r for r in report["sources"]}
    assert by_provider["talentreef"]["coverage_status"]=="UNSEEDED"
    assert by_provider["talentreef"]["collector_class"]=="native_client_scoped"
    assert by_provider["jobappnetwork"]["coverage_status"]=="UNSEEDED"
    assert report["coverage_counts"]["UNSEEDED"] >= 2


def test_source_health_encodes_learned_ashby_board_name(tmp_path, monkeypatch):
    cfg={"ashby":[]}
    p=tmp_path/"sources.json"
    p.write_text(json.dumps(cfg),encoding="utf-8")
    monkeypatch.setattr(source_health,"ROOT",Path(tmp_path))
    monkeypatch.setattr(source_health,"load_registry",lambda: {"ashby":[{"company":"Superhuman Platform Inc","board_name":"superhuman platform inc"}]})
    monkeypatch.setattr(source_health,"as_discovery_config",lambda registry: registry)
    seen=[]
    monkeypatch.setattr(source_health,"_probe",lambda url,timeout=12,**kwargs: seen.append(url) or {"status":"ok","http_status":200})
    report=source_health.run("sources.json",timeout=1)
    ashby=[r for r in report["sources"] if r["provider"]=="ashby"]
    assert ashby
    assert ashby[0]["target"].endswith("/superhuman%20platform%20inc")
    assert seen[0].endswith("/superhuman%20platform%20inc")
