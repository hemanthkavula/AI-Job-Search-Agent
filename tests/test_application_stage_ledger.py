from app.application_stage import _record_result


def _item():
    return {
        "external_id": "example:1",
        "source": "workday",
        "company": "Example Employer",
        "title": "Senior Data Engineer",
        "url": "https://example.com/jobs/1",
    }


def _status(ledger):
    rows = list((ledger.get("jobs") or {}).values())
    assert len(rows) == 1
    return rows[0]


def test_confirmed_submission_is_terminal_in_ledger():
    ledger = {"jobs": {}}
    _record_result(_item(), {"status": "SUBMITTED", "agent_result": "Application submitted"}, ledger)
    row = _status(ledger)
    assert row["application_status"] == "SUBMITTED_CONFIRMED"
    assert row.get("submitted_at")


def test_ambiguous_submit_is_not_marked_applied():
    ledger = {"jobs": {}}
    _record_result(_item(), {"status": "SUBMISSION_ATTEMPTED", "agent_result": "No confirmation"}, ledger)
    row = _status(ledger)
    assert row["application_status"] == "SUBMISSION_ATTEMPTED"
    assert row["submission_attempted"] is True


def test_setup_failure_preserves_ready_state_for_retry():
    ledger = {"jobs": {}}
    _record_result(_item(), {"status": "SETUP_REQUIRED", "error": "browser missing"}, ledger)
    assert not ledger.get("jobs")
