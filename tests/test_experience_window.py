from app.eligibility import experience_check


PROFILE = {
    "candidate_experience_years": 5,
    "preferences": {"min_required_years": 4, "max_required_years": 7},
}


def _job(years: int) -> dict:
    return {
        "title": "Senior Data Engineer",
        "description": f"Requires {years}+ years of professional experience in data engineering.",
    }


def test_experience_window_accepts_requirements_candidate_meets():
    for years in (4, 5):
        result = experience_check(_job(years), PROFILE)
        assert result["eligible"] is True, years
        assert result["category"] == "EXPERIENCE_ELIGIBLE", years
        assert result["configured_window"] == [4, 7]
        assert result["effective_max_required_years"] == 5


def test_experience_window_rejects_requirement_above_candidate_years():
    for years in (6, 7):
        result = experience_check(_job(years), PROFILE)
        assert result["eligible"] is False, years
        assert result["category"] == "EXPERIENCE_TOO_SENIOR", years
        assert result["candidate_years"] == 5


def test_experience_window_rejects_below_four():
    result = experience_check(_job(3), PROFILE)
    assert result["eligible"] is False
    assert result["category"] == "EXPERIENCE_TOO_JUNIOR"


def test_experience_window_rejects_above_seven():
    result = experience_check(_job(8), PROFILE)
    assert result["eligible"] is False
    assert result["category"] == "EXPERIENCE_TOO_SENIOR"
