from app.job_ledger import record_seen, seen_or_submitted
from app import dashboard


def test_manual_ready_is_terminal_for_duplicate_resume_generation():
    ledger={"jobs":{}}
    job={"external_id":"manatal:1","source":"manatal","company_key":"Example Inc","title":"Data Engineer","location":"United States","url":"https://example.test/jobs/1"}
    record_seen(job,ledger,"MANUAL_READY_TO_APPLY")
    seen,key,row=seen_or_submitted(job,ledger)
    assert seen is True
    assert row["application_status"]=="MANUAL_READY_TO_APPLY"


def test_dashboard_exposes_manual_ready_stage(monkeypatch,tmp_path):
    monkeypatch.setattr(dashboard,"LEDGER",tmp_path/"ledger.json")
    monkeypatch.setattr(dashboard,"CONFIRMED",tmp_path/"confirmed.json")
    monkeypatch.setattr(dashboard,"HIDDEN",tmp_path/"hidden.json")
    monkeypatch.setattr(dashboard,"CYCLES",tmp_path/"cycles")
    (tmp_path/"ledger.json").write_text('{"jobs":{"job:1":{"company":"Example Inc","title":"Data Engineer","source":"manatal","url":"https://example.test/jobs/1","application_status":"MANUAL_READY_TO_APPLY","first_seen":"2026-09-26T12:00:00+00:00","last_seen":"2026-09-26T12:00:00+00:00"}}}',encoding="utf-8")
    rows=dashboard._jobs()
    assert len(rows)==1
    assert rows[0]["stage"]=="Manual apply"
