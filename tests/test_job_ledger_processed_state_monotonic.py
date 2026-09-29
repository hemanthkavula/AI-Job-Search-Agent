from app.job_ledger import record_seen


def _job():
    return {
        "external_id": "greenhouse:123",
        "source": "greenhouse",
        "company_key": "Example Co",
        "title": "Data Engineer",
        "url": "https://boards.greenhouse.io/example/jobs/123",
    }


def test_rediscovery_does_not_regress_ready_to_apply():
    ledger={"jobs":{},"aliases":{}}
    job=_job()
    record_seen(job,ledger,"READY_TO_APPLY")
    record_seen(job,ledger,"DISCOVERED")
    row=next(iter(ledger["jobs"].values()))
    assert row["application_status"]=="READY_TO_APPLY"


def test_rediscovery_does_not_regress_ats_hold():
    ledger={"jobs":{},"aliases":{}}
    job=_job()
    record_seen(job,ledger,"HOLD_ATS_REVIEW")
    record_seen(job,ledger,"ELIGIBLE_FOR_RESUME")
    row=next(iter(ledger["jobs"].values()))
    assert row["application_status"]=="HOLD_ATS_REVIEW"
