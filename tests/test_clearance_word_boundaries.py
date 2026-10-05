from app.eligibility import clearance_check


def test_clearance_parser_does_not_match_stakeholder_and_disciplined_substrings():
    job = {
        "title": "Senior Data Engineer",
        "description": (
            "Partner with stakeholder responsibilities through disciplined business practices. "
            "Build secure data platforms and follow standard security controls."
        ),
    }
    result = clearance_check(job, {})
    assert result["eligible"] is True
    assert result["category"] == "CLEARANCE_NOT_REQUIRED"


def test_clearance_parser_still_rejects_explicit_secret_clearance_requirement():
    job = {
        "title": "Senior Data Engineer",
        "description": "Candidate must hold an active Secret security clearance and maintain it during employment.",
    }
    result = clearance_check(job, {})
    assert result["eligible"] is False
    assert result["category"] == "CLEARANCE_REQUIRED"
