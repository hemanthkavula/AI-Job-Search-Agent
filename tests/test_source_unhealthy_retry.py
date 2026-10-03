import json
from datetime import datetime, timezone, timedelta

import app.discovery as discovery


def _quiet_discovery_dependencies(monkeypatch):
    monkeypatch.setattr(discovery,"load_registry",lambda *_:{})
    monkeypatch.setattr(discovery,"as_discovery_config",lambda *_:{})
    monkeypatch.setattr(discovery,"annotate_jobs",lambda rows:rows)
    monkeypatch.setattr(discovery,"learn_from_jobs",lambda *args:[])
    monkeypatch.setattr(discovery,"load_company_registry",lambda :{})
    monkeypatch.setattr(discovery,"learn_companies_from_jobs",lambda *args:[])
    monkeypatch.setattr(discovery,"save_company_registry",lambda *args:None)


def test_unhealthy_source_is_skipped_until_retry_ttl_then_retried(tmp_path, monkeypatch):
    _quiet_discovery_dependencies(monkeypatch)
    health_path=tmp_path/"source_health.json"
    retry_path=tmp_path/"source_retry_state.json"
    health_path.write_text(json.dumps({
        "sources":[{
            "provider":"greenhouse",
            "company":"Acme",
            "status":"blocked_or_http_error",
        }]
    }),encoding="utf-8")

    calls=[]
    monkeypatch.setattr(discovery,"greenhouse_jobs",lambda token:calls.append(token) or [])
    config={"greenhouse":[{"company":"Acme","board_token":"acme"}]}
    now=datetime.now(timezone.utc)
    retry_path.write_text(json.dumps({
        "greenhouse:Acme":{
            "source":"greenhouse",
            "company":"Acme",
            "last_retry_at":now.isoformat(),
        }
    }),encoding="utf-8")

    _,_,coverage=discovery.discover(
        config,registry_path=str(tmp_path/"registry.json"),
        health_path=str(health_path),source_retry_path=str(retry_path),
        unhealthy_retry_hours=6,return_coverage=True,
    )
    assert calls==[]
    assert coverage["skipped_unhealthy_units"]==1

    retry_path.write_text(json.dumps({
        "greenhouse:Acme":{
            "source":"greenhouse",
            "company":"Acme",
            "last_retry_at":(now-timedelta(hours=7)).isoformat(),
        }
    }),encoding="utf-8")
    discovery.discover(
        config,registry_path=str(tmp_path/"registry.json"),
        health_path=str(health_path),source_retry_path=str(retry_path),
        unhealthy_retry_hours=6,return_coverage=True,
    )
    assert calls==["acme"]


def test_manual_provider_check_forces_retry_even_inside_ttl(tmp_path, monkeypatch):
    _quiet_discovery_dependencies(monkeypatch)
    health_path=tmp_path/"source_health.json"
    retry_path=tmp_path/"source_retry_state.json"
    health_path.write_text(json.dumps({
        "sources":[{"provider":"greenhouse","company":"Acme","status":"broken"}]
    }),encoding="utf-8")
    retry_path.write_text(json.dumps({
        "greenhouse:Acme":{"last_retry_at":datetime.now(timezone.utc).isoformat()}
    }),encoding="utf-8")
    calls=[]
    monkeypatch.setattr(discovery,"greenhouse_jobs",lambda token:calls.append(token) or [])
    discovery.discover(
        {"greenhouse":[{"company":"Acme","board_token":"acme"}]},
        only_source="greenhouse",registry_path=str(tmp_path/"registry.json"),
        health_path=str(health_path),source_retry_path=str(retry_path),
        unhealthy_retry_hours=6,
    )
    assert calls==["acme"]
