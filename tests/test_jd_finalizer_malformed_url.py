from app import jd_finalizer


def test_malformed_url_is_held_not_raised():
    status, reason = jd_finalizer._live_public_job_page(
        "https://example.com/superhuman platform inc/4c9e87f9-6fa1-4969-90bf-1cab630a0275"
    )
    assert status is None
    assert reason == "unverifiable"
