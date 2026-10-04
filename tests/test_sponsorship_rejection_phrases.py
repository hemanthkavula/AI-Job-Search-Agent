from app.eligibility import sponsorship_check, two_category_filter

PROFILE = {
    "candidate_experience_years": 5,
    "preferences": {"min_required_years": 4, "max_required_years": 7},
    "work_authorization": {
        "requires_sponsorship_now": False,
        "requires_sponsorship_future": False,
    },
}


def _job(description):
    return {
        "title": "Data Engineer III",
        "description": description,
    }


def test_explicit_no_sponsorship_is_informational_not_rejection():
    result = sponsorship_check(
        _job("Additional Information. Visa sponsorship is not available for this position."),
        PROFILE,
    )
    assert result["eligible"] is True
    assert result["category"] == "SPONSORSHIP_UNAVAILABLE_INFORMATIONAL"


def test_common_no_sponsorship_variants_all_proceed():
    phrases = [
        "Visa sponsorship not available for this role.",
        "Sponsorship is not available for this position.",
        "We do not provide visa sponsorship.",
        "The company will not offer employment visa sponsorship.",
        "Candidates must be authorized to work in the U.S. without current or future visa sponsorship.",
        "Current or future sponsorship is not available.",
        "This role is not eligible for F-1 OPT or STEM OPT sponsorship support.",
    ]
    for phrase in phrases:
        result = sponsorship_check(_job(phrase), PROFILE)
        assert result["eligible"] is True, phrase
        assert result["category"] == "SPONSORSHIP_UNAVAILABLE_INFORMATIONAL", phrase


def test_no_sponsorship_does_not_block_full_eligibility():
    result = two_category_filter(
        _job("Requires 5 years of experience. Visa sponsorship is not available for this position."),
        PROFILE,
    )
    assert result["eligible"] is True
    assert result["sponsorship"]["eligible"] is True
    assert result["sponsorship"]["category"] == "SPONSORSHIP_UNAVAILABLE_INFORMATIONAL"


def test_unknown_sponsorship_still_proceeds():
    result = sponsorship_check(
        _job("Build scalable data pipelines using Python, Spark, and SQL."),
        PROFILE,
    )
    assert result["eligible"] is True
    assert result["category"] == "SPONSORSHIP_NOT_STATED"


def test_positive_sponsorship_language_is_informational_only():
    result = sponsorship_check(
        _job("H-1B sponsorship is available for qualified candidates."),
        PROFILE,
    )
    assert result["eligible"] is True
    assert result["category"] == "SPONSORSHIP_AVAILABLE_INFORMATIONAL"
