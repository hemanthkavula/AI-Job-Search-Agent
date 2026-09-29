from app.eligibility import experience_check


def test_compact_year_requirement_is_rejected():
    profile = {"candidate_experience_years": 5, "preferences": {"min_required_years": 3, "max_required_years": 7}}
    job = {"title": "Senior Data Engineer", "description": "Basic Required Qualifications: 10+y of relevant experience with building data environments such as AWS."}
    result = experience_check(job, profile)
    assert result["required_years"] == 10
    assert result["category"] == "EXPERIENCE_TOO_SENIOR"
    assert result["eligible"] is False


def test_later_higher_overall_requirement_cannot_be_hidden_by_earlier_range():
    profile = {"candidate_experience_years": 5, "preferences": {"min_required_years": 3, "max_required_years": 7}}
    job = {
        "title": "Senior Data Engineer",
        "description": "3-5 years of relevant experience with Python. 10+ years of professional experience required overall."
    }
    result = experience_check(job, profile)
    assert result["required_years"] == 10
    assert result["category"] == "EXPERIENCE_TOO_SENIOR"
    assert result["eligible"] is False


def _profile():
    return {"candidate_experience_years": 5, "preferences": {"min_required_years": 3, "max_required_years": 7}}


def test_three_year_minimum_is_eligible():
    result = experience_check(
        {"title": "Data Engineer", "description": "3+ years of professional experience required."},
        _profile(),
    )
    assert result["required_years"] == 3
    assert result["category"] == "EXPERIENCE_ELIGIBLE"
    assert result["eligible"] is True


def test_configured_maximum_is_inclusive():
    result = experience_check(
        {"title": "Senior Data Engineer", "description": "7+ years of professional experience required."},
        _profile(),
    )
    assert result["required_years"] == 7
    assert result["eligible"] is True


def test_above_configured_maximum_is_rejected():
    result = experience_check(
        {"title": "Senior Data Engineer", "description": "8+ years of professional experience required."},
        _profile(),
    )
    assert result["required_years"] == 8
    assert result["category"] == "EXPERIENCE_TOO_SENIOR"
    assert result["eligible"] is False


def test_unstated_experience_remains_eligible_for_later_verification():
    result = experience_check(
        {"title": "Data Engineer", "description": "Build reliable Spark and SQL data pipelines."},
        _profile(),
    )
    assert result["required_years"] is None
    assert result["category"] == "EXPERIENCE_NOT_STATED"
    assert result["eligible"] is True


def test_below_three_year_minimum_is_rejected():
    result = experience_check(
        {"title": "Data Engineer", "description": "2+ years of professional experience required."},
        _profile(),
    )
    assert result["required_years"] == 2
    assert result["category"] == "EXPERIENCE_TOO_JUNIOR"
    assert result["eligible"] is False
