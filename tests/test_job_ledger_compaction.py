from app.job_ledger import compact_ledger

def test_compaction_preserves_identity_state_and_operational_fields():
    ledger={
        "jobs":{"job-1":{
            "first_seen":"a","last_seen":"b","company":"Acme","title":"Data Engineer",
            "source":"lever","url":"https://example.test/job","application_status":"READY_TO_APPLY",
            "external_ids":["1"],"sources":["lever"],"queue_item":{"external_id":"1","resume_path":"x.pdf"},
            "retry_application":{"external_id":"1","resume_path":"x.pdf"},
            "large_obsolete_payload":{"description":"unused"},
        }},
        "aliases":{"external:1":"job-1"},
    }
    out,stats=compact_ledger(ledger)
    row=out["jobs"]["job-1"]
    assert out["aliases"]==ledger["aliases"]
    assert row["application_status"]=="READY_TO_APPLY"
    assert row["queue_item"]==ledger["jobs"]["job-1"]["queue_item"]
    assert row["retry_application"]==ledger["jobs"]["job-1"]["retry_application"]
    assert "large_obsolete_payload" not in row
    assert stats["removed_fields"]==1

def test_compaction_keeps_submitted_history():
    ledger={"jobs":{"j":{"company":"Acme","title":"DE","application_status":"SUBMITTED_CONFIRMED","submitted_at":"2026-09-19","submission_attempt":{"url":"x"},"noise":"x"}},"aliases":{}}
    out,_=compact_ledger(ledger)
    row=out["jobs"]["j"]
    assert row["application_status"]=="SUBMITTED_CONFIRMED"
    assert row["submitted_at"]=="2026-09-19"
    assert row["submission_attempt"]=={"url":"x"}
