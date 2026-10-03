from pathlib import Path

from app.application_stage import build_task, classify_result
from app.application_queue import _application_gate


PROFILE = {
    "name": "Hemanth Kavula",
    "candidate_experience_years": 5,
    "contact": {"email": "test@example.com", "phone": "+1 555 555 5555"},
    "preferences": {"min_required_years": 3, "max_required_years": 7},
    "work_authorization": {
        "authorized_to_work_us": True,
        "requires_sponsorship_now": False,
        "requires_sponsorship_future": True,
    },
    "application_preferences": {},
}


def _queue_item(description="Build Python SQL Spark data pipelines. Full-Time."):
    return {
        "external_id": "example:1",
        "source": "workday",
        "company": "Example Employer",
        "title": "Senior Data Engineer",
        "location": "New York, NY, United States",
        "employment_type": "Full-Time",
        "description": description,
        "url": "https://example.com/jobs/1",
        "known_answers": {
            "authorized_to_work_us": "Yes",
            "requires_sponsorship_now": "No",
            "requires_future_sponsorship": "Yes",
        },
    }


def test_application_task_keeps_sponsorship_truthful_but_non_blocking():
    task = build_task(_queue_item(), PROFILE, Path("/tmp/resume.pdf"), allow_submit=True)
    assert "sponsorship now/currently=NO" in task
    assert "sponsorship in future=YES" in task
    assert "no-sponsorship/no-future-sponsorship/no-immigration-support" in task
    assert "is NOT an eligibility blocker" in task


def test_submitted_requires_visible_confirmation_text():
    assert classify_result("SUBMITTED\nApplication submitted. Thank you for applying.") == "SUBMITTED"
    assert classify_result("SUBMITTED\nClicked submit but no confirmation appeared.") == "SUBMISSION_ATTEMPTED"


def test_manual_and_ineligible_terminal_states_are_preserved():
    assert classify_result("MANUAL_ACTION_REQUIRED\nCAPTCHA shown") == "MANUAL_ACTION_REQUIRED"
    assert classify_result("INELIGIBLE_AT_APPLICATION\nU.S. citizenship required") == "INELIGIBLE_AT_APPLICATION"


def test_no_sponsorship_language_passes_pre_submit_gate():
    item = _queue_item(
        "Build Python SQL Spark data pipelines. Full-Time. "
        "Visa sponsorship is not available now or in the future."
    )
    ok, reasons = _application_gate(item, PROFILE)
    assert ok, reasons


def test_citizenship_and_clearance_remain_pre_submit_blockers():
    citizen = _queue_item("Build Python SQL Spark data pipelines. Full-Time. U.S. citizenship required.")
    ok, reasons = _application_gate(citizen, PROFILE)
    assert not ok and any("citizenship" in reason.lower() for reason in reasons)

    clearance = _queue_item("Build Python SQL Spark data pipelines. Full-Time. Security clearance required.")
    ok, reasons = _application_gate(clearance, PROFILE)
    assert not ok and any("clearance" in reason.lower() for reason in reasons)
