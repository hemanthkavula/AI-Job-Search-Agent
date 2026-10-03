from app.eligibility import sponsorship_check, two_category_filter

PROFILE = {
    "candidate_experience_years": 5,
    "preferences": {"min_required_years": 4, "max_required_years": 7},
    "work_authorization": {"requires_sponsorship_future": True},
}


def _job(description):
    return {
        "title": "Data Engineer III",
        "description": description,
    }


def test_hntb_exact_no_sponsorship_phrase_is_recorded_but_allowed():
    result = sponsorship_check(
        _job("Additional Information. Visa sponsorship is not available for this position."),
        PROFILE,
    )
    assert result["eligible"] is True
    assert result["category"] == "NO_SPONSORSHIP"


def test_common_no_sponsorship_variants_are_allowed():
    phrases = [
        "Visa sponsorship not available for this role.",
        "Sponsorship is not available for this position.",
        "We do not provide visa sponsorship.",
        "The company will not offer employment visa sponsorship.",
        "Candidates must be authorized to work in the U.S. without current or future visa sponsorship.",
        "Current or future sponsorship is not available.",
    ]
    for phrase in phrases:
        result = sponsorship_check(_job(phrase), PROFILE)
        assert result["eligible"] is True, phrase
        assert result["category"] == "NO_SPONSORSHIP", phrase


def test_no_sponsorship_does_not_block_full_eligibility():
    result = two_category_filter(
        _job("Requires 5 years of experience. Visa sponsorship is not available for this position."),
        PROFILE,
    )
    assert result["eligible"] is True
    assert result["sponsorship"]["category"] == "NO_SPONSORSHIP"


def test_unknown_sponsorship_still_proceeds():
    result = sponsorship_check(
        _job("Build scalable data pipelines using Python, Spark, and SQL."),
        PROFILE,
    )
    assert result["eligible"] is True
    assert result["category"] == "SPONSORSHIP_NOT_STATED"


def test_citizenship_requirement_still_blocks_even_when_no_sponsorship_is_allowed():
    result = two_category_filter(
        _job(
            "Requires 5 years of experience. Visa sponsorship is not available. "
            "U.S. citizenship is required."
        ),
        PROFILE,
    )
    assert result["eligible"] is False
    assert result["sponsorship"]["eligible"] is True
    assert result["citizenship"]["category"] == "US_CITIZENSHIP_REQUIRED"


def test_clearance_requirement_still_blocks_even_when_no_sponsorship_is_allowed():
    result = two_category_filter(
        _job(
            "Requires 5 years of experience. Visa sponsorship is not available. "
            "Security clearance required."
        ),
        PROFILE,
    )
    assert result["eligible"] is False
    assert result["sponsorship"]["eligible"] is True
    assert result["clearance"]["category"] == "CLEARANCE_REQUIRED"
