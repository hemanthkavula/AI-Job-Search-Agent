from app.llm_job_analyzer import _validated, semantic_rejection_reasons

PROFILE={"candidate_experience_years":5,"preferences":{"min_required_years":4,"max_required_years":7}}

def test_semantic_ten_year_requirement_rejects_when_evidence_is_in_official_jd():
    jd="Basic Required Qualifications: 10+y of relevant experience with building AI and data environments such as AWS."
    raw={
        "required_experience_years":10,
        "required_experience_evidence":"10+y of relevant experience",
        "employment_type":"full_time",
        "sponsorship":"unknown",
        "us_citizenship_required":None,
        "clearance_required":None,
        "role_family":"data_engineering",
        "role_family_evidence":"data environments",
    }
    analysis=_validated(raw,jd)
    assert analysis["required_experience_years"]==10
    reasons=semantic_rejection_reasons(analysis,PROFILE)
    assert any("10+ years" in reason for reason in reasons)

def test_semantic_restriction_without_literal_jd_evidence_is_not_trusted():
    jd="Build reliable data pipelines using Python, Spark and AWS."
    raw={
        "required_experience_years":10,
        "required_experience_evidence":"10+ years of experience",
        "employment_type":"contract",
        "employment_evidence":"6 month contract",
        "sponsorship":"unavailable",
        "sponsorship_evidence":"no sponsorship",
        "us_citizenship_required":True,
        "citizenship_evidence":"US citizens only",
        "clearance_required":True,
        "clearance_evidence":"Secret clearance required",
        "role_family":"data_engineering",
        "role_family_evidence":"data pipelines",
    }
    analysis=_validated(raw,jd)
    assert analysis["required_experience_years"] is None
    assert analysis["employment_evidence"] is None
    assert analysis["sponsorship"]=="unknown"
    assert analysis["us_citizenship_required"] is None
    assert analysis["clearance_required"] is None
    assert semantic_rejection_reasons(analysis,PROFILE)==[]

def test_semantic_seven_year_requirement_remains_eligible():
    jd="Requires 7 years of professional experience in data engineering."
    analysis=_validated({
        "required_experience_years":7,
        "required_experience_evidence":"7 years of professional experience",
        "employment_type":"full_time",
        "sponsorship":"unknown",
        "us_citizenship_required":None,
        "clearance_required":None,
        "role_family":"data_engineering",
        "role_family_evidence":"data engineering",
    },jd)
    assert semantic_rejection_reasons(analysis,PROFILE)==[]
