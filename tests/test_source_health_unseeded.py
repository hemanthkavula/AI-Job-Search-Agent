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
