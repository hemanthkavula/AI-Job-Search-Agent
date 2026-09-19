from app.job_ledger import load_ledger, record_seen


def test_new_ledger_has_versioned_structure(tmp_path):
    ledger=load_ledger(tmp_path/"missing.json")
    assert ledger["schema_version"] == 2
    assert ledger["jobs"] == {}
    assert ledger["aliases"] == {}


def test_record_seen_tracks_canonical_lifecycle_fields():
    ledger={"schema_version":2,"jobs":{},"aliases":{}}
    job={
        "external_id":"lever:example:123","source":"lever","company_key":"Example",
        "title":"Data Engineer","location":"Remote - US","url":"https://jobs.example/123",
        "apply_url":"https://jobs.example/123/apply","posted_at":"2026-09-19T12:00:00Z",
        "description":"Python SQL Spark data pipelines"
    }
    key=record_seen(job,ledger,"DISCOVERED")
    row=ledger["jobs"][key]
    assert row["first_seen_at"]
    assert row["last_seen_at"]
    assert row["external_job_id"] == "lever:example:123"
    assert row["posted_at"] == "2026-09-19T12:00:00Z"
    assert row["description_hash"]
    assert row["job_url"] == "https://jobs.example/123"
    assert row["apply_url"] == "https://jobs.example/123/apply"
    assert row["application_status"] == "DISCOVERED"
