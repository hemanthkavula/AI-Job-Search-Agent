from datetime import datetime, timezone
import json
from pathlib import Path

from app import discovery


def test_generic_ats_units_use_independent_watermark_windows(monkeypatch, tmp_path):
    now=datetime.now(timezone.utc)
    def fake_public(company, url, provider, pattern):
        return [
            {"external_id":company+":old","source":provider,"company_key":company,"title":"Data Engineer","url":url+"/old","posted_at":(now.replace(microsecond=0)).isoformat()},
        ]
    # Make HealthyCo's item older than its one-hour unit window but inside BrokenCo's four-hour catch-up window.
    old=(now.timestamp()-2*3600)
    def fake_public(company, url, provider, pattern):
        stamp=datetime.fromtimestamp(old,timezone.utc).isoformat()
        return [{"external_id":company+":job","source":provider,"company_key":company,"title":"Data Engineer","url":url+"/job","posted_at":stamp}]
    monkeypatch.setattr(discovery,"public_ats_jobs",fake_public)
    monkeypatch.setattr(discovery,"annotate_jobs",lambda rows:rows)
    monkeypatch.setattr(discovery,"load_registry",lambda path:{})
    monkeypatch.setattr(discovery,"as_discovery_config",lambda registry:{})
    monkeypatch.setattr(discovery,"learn_from_jobs",lambda jobs,registry:[])
    monkeypatch.setattr(discovery,"load_company_registry",lambda:{})
    monkeypatch.setattr(discovery,"learn_companies_from_jobs",lambda jobs,registry:[])
    monkeypatch.setattr(discovery,"save_company_registry",lambda registry:None)
    cfg={"bamboohr":[
        {"company":"HealthyCo","search_url":"https://healthy.example/careers","job_url_pattern":r".+"},
        {"company":"BrokenCo","search_url":"https://broken.example/careers","job_url_pattern":r".+"},
    ]}
    result=discovery.discover(cfg,registry_path=str(tmp_path/"registry.json"),health_path=str(tmp_path/"health.json"),source_unit_hours={"bamboohr:HealthyCo":1.0,"bamboohr:BrokenCo":4.0})
    assert isinstance(result,tuple) and len(result) == 2
    rows,errors=result
    assert errors == []
    assert [r["company_key"] for r in rows] == ["BrokenCo"]
    health=json.loads(Path(tmp_path/"health.json").read_text())
    assert health["bamboohr:HealthyCo"]["unit_window_hours"] == 1.0
    assert health["bamboohr:BrokenCo"]["unit_window_hours"] == 4.0
