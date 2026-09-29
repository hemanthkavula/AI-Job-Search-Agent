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


def test_compaction_preserves_authoritative_location_and_ats_identity():
    ledger={"jobs":{"j":{
        "company":"Acme","title":"Data Engineer","source":"lever","url":"https://jobs.example/1",
        "original_url":"https://jobs.lever.co/acme/1","application_status":"READY_TO_APPLY",
        "location":"Remote - United States","official_location":"Remote - United States",
        "discovery_location":"Remote","location_basis":"official_employer_jobposting",
        "employment_type":"Full-Time","ats_provider":"lever","ats_identifier":"acme",
        "requisition_id":"REQ-1","application_route":"EXTERNAL_ATS","noise":"drop-me"
    }},"aliases":{"req:req-1":"j"}}
    out,_=compact_ledger(ledger)
    row=out["jobs"]["j"]
    for key in ("original_url","location","official_location","discovery_location","location_basis",
                "employment_type","ats_provider","ats_identifier","requisition_id","application_route"):
        assert row[key]==ledger["jobs"]["j"][key]
    assert "noise" not in row
