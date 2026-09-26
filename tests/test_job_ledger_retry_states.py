from app.job_ledger import retryable_jobs


def test_only_resume_retry_state_can_enter_resume_recovery():
    ledger={"jobs":{
        "ready":{"application_status":"READY_TO_APPLY","retry_job":{"external_id":"ready:1"}},
        "manual":{"application_status":"MANUAL_READY_TO_APPLY","retry_job":{"external_id":"manual:1"}},
        "progress":{"application_status":"APPLICATION_IN_PROGRESS","retry_job":{"external_id":"progress:1"}},
        "application-retry":{"application_status":"RETRY_APPLICATION","retry_job":{"external_id":"application:1"}},
        "resume-retry":{"application_status":"RETRY_RESUME_GENERATION","retry_job":{"external_id":"retry:1"}},
    }}
    rows=retryable_jobs(ledger)
    assert [x["external_id"] for x in rows]==["retry:1"]
