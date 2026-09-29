import json
import pytest

from app.job_ledger import load_ledger, save_ledger


def test_existing_corrupt_ledger_fails_closed(tmp_path):
    path=tmp_path/"job_ledger.json"
    path.write_text("{not-json",encoding="utf-8")
    with pytest.raises(RuntimeError,match="corrupt"):
        load_ledger(path)


def test_invalid_ledger_structure_fails_closed(tmp_path):
    path=tmp_path/"job_ledger.json"
    path.write_text(json.dumps({"jobs":[]}),encoding="utf-8")
    with pytest.raises(RuntimeError,match="invalid structure"):
        load_ledger(path)


def test_atomic_ledger_save_leaves_valid_json_and_no_temp(tmp_path):
    path=tmp_path/"job_ledger.json"
    payload={"jobs":{"x":{"application_status":"READY_TO_APPLY"}}}
    save_ledger(payload,path)
    assert load_ledger(path)==payload
    assert not path.with_name(path.name+".tmp").exists()


def test_record_seen_does_not_regress_terminal_application_state():
    from app.job_ledger import record_seen
    job={"external_id":"lever:123","source":"lever","company_key":"Acme","title":"Data Engineer","url":"https://jobs.example/123"}
    ledger={"jobs":{}}
    record_seen(job,ledger,"SUBMITTED_CONFIRMED",submitted_at="2026-09-29T12:00:00+00:00")
    record_seen(job,ledger,"DISCOVERED")
    key=next(iter(ledger["jobs"]))
    assert ledger["jobs"][key]["application_status"]=="SUBMITTED_CONFIRMED"
    record_seen(job,ledger,"ELIGIBLE_FOR_RESUME")
    assert ledger["jobs"][key]["application_status"]=="SUBMITTED_CONFIRMED"
