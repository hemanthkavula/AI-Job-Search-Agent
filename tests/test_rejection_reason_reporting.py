from app.daily_runner import _reason_key


def test_reason_keys_are_reported_in_specific_buckets():
    cases={
        "title/JD outside data-engineering job family":"wrong_job_family",
        "location outside United States target":"location_outside_us",
        "employment type outside Full-Time/W-2 target":"employment_type_mismatch",
        "experience requirement not met: 10 years required":"experience_mismatch",
        "future H-1B sponsorship unavailable":"no_future_sponsorship",
        "US citizenship required":"citizenship_restriction",
        "security/public-trust clearance required":"clearance_restriction",
        "excluded prior employer":"excluded_prior_employer",
    }
    for reason,expected in cases.items():
        assert _reason_key(reason)==expected


def test_unknown_reason_remains_other_hard_filter():
    assert _reason_key("some new future restriction")=="other_hard_filter"
