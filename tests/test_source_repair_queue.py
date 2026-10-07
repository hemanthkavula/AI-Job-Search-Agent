import json
from datetime import datetime, timezone

from app import source_reliability, source_repair


NOW=datetime(2026,10,7,15,0,tzinfo=timezone.utc)


def test_repair_queue_replaces_failed_learned_source_and_releases_retry(monkeypatch,tmp_path):
    retry_path=tmp_path/"retry.json"
    queue_path=tmp_path/"repair.json"
    key="oracle:Dead Co"
    source_reliability._save({
        "version":1,
        "units":{
            key:{
                "source":"oracle","company":"Dead Co","consecutive_failures":1,
                "failure_class":"hard","repair_required":True,"last_error":"HTTP 404",
            }
        },
    },retry_path)

    company_registry={"dead":{"company":"Dead Co","official_domain":"dead.example"}}
    source_registry={
        "oracle":[{"company":"Dead Co","identifier":"old","search_url":"https://old.example/jobs"}],
        "greenhouse":[],
    }
    saved={}

    monkeypatch.setattr(source_repair,"load_company_registry",lambda:company_registry)
    monkeypatch.setattr(source_repair,"load_source_registry",lambda:source_registry)
    monkeypatch.setattr(source_repair,"save_company_registry",lambda reg:saved.setdefault("companies",reg))
    monkeypatch.setattr(source_repair,"save_source_registry",lambda reg:saved.setdefault("sources",reg))
    monkeypatch.setattr(source_repair,"company_key",lambda value:"dead")
    monkeypatch.setattr(source_repair,"_resolve_replacement",lambda company,row:({
        "careers_url":"https://boards.greenhouse.io/deadco",
        "ats_provider":"greenhouse",
        "ats_identifier":"deadco",
    },row))

    result=source_repair.repair(
        limit=10,queue_path=queue_path,retry_state_path=retry_path,now=NOW
    )

    assert result["repaired"]==1
    assert source_registry["oracle"]==[]
    assert source_registry["greenhouse"][0]["company"]=="Dead Co"
    queue=json.loads(queue_path.read_text())
    assert queue["items"][key]["status"]=="REPAIRED"
    retry=json.loads(retry_path.read_text())
    assert retry["units"][key]["repair_required"] is False
    assert retry["units"][key]["consecutive_failures"]==0
