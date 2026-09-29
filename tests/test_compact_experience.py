from app.eligibility import experience_check


def test_compact_year_requirement_is_rejected():
    profile = {"candidate_experience_years": 5, "preferences": {"min_required_years": 4, "max_required_years": 7}}
    job = {"title": "Senior Data Engineer", "description": "Basic Required Qualifications: 10+y of relevant experience with building data environments such as AWS."}
    result = experience_check(job, profile)
    assert result["required_years"] == 10
    assert result["category"] == "EXPERIENCE_TOO_SENIOR"
    assert result["eligible"] is False


def test_later_higher_overall_requirement_cannot_be_hidden_by_earlier_range():
    profile = {"candidate_experience_years": 5, "preferences": {"min_required_years": 4, "max_required_years": 7}}
    job = {
        "title": "Senior Data Engineer",
        "description": "3-5 years of relevant experience with Python. 10+ years of professional experience required overall."
    }
    result = experience_check(job, profile)
    assert result["required_years"] == 10
    assert result["category"] == "EXPERIENCE_TOO_SENIOR"
    assert result["eligible"] is False
