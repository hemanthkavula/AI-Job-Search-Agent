import json
from app import source_health

def test_source_health_includes_learned_sources(tmp_path, monkeypatch):
    cfg={"greenhouse":[],"career_site":[]}
    p=tmp_path/"sources.json"
    p.write_text(json.dumps(cfg),encoding="utf-8")
    monkeypatch.setattr(source_health,"load_registry",lambda: {"greenhouse":[{"company":"Learned Co","board_token":"learned"}]})
    monkeypatch.setattr(source_health,"as_discovery_config",lambda reg: {"greenhouse":[{"company":"Learned Co","board_token":"learned"}]})
    monkeypatch.setattr(source_health,"_probe",lambda *a,**k: {"status":"ok","http_status":200})
    report=source_health.run(str(p))
    assert any(x["provider"]=="greenhouse" and x["company"]=="Learned Co" for x in report["sources"])
