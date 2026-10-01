from app.llm_job_analyzer import _validated, semantic_rejection_reasons

PROFILE={"candidate_experience_years":5,"preferences":{"min_required_years":3,"max_required_years":7}}

def _analysis(years,jd):
    return _validated({"required_experience_years":years,"required_experience_evidence":f"{years} years of professional experience","employment_type":"full_time","sponsorship":"unknown","us_citizenship_required":None,"clearance_required":None,"role_family":"data_engineering","role_family_evidence":"data engineering"},jd)

def test_semantic_ten_year_requirement_rejects_when_evidence_is_in_official_jd():
    jd="Basic Required Qualifications: 10 years of professional experience in data engineering."
    analysis=_analysis(10,jd);assert analysis["required_experience_years"]==10;assert any("10+ years" in r for r in semantic_rejection_reasons(analysis,PROFILE))

def test_semantic_restriction_without_literal_jd_evidence_is_not_trusted():
    jd="Build reliable data pipelines using Python, Spark and AWS."
    raw={"required_experience_years":10,"required_experience_evidence":"10+ years of experience","employment_type":"contract","employment_evidence":"6 month contract","sponsorship":"unavailable","sponsorship_evidence":"no sponsorship","us_citizenship_required":True,"citizenship_evidence":"US citizens only","clearance_required":True,"clearance_evidence":"Secret clearance required","role_family":"data_engineering","role_family_evidence":"data pipelines"}
    analysis=_validated(raw,jd);assert analysis["required_experience_years"] is None;assert analysis["employment_evidence"] is None;assert analysis["sponsorship"]=="unknown";assert analysis["us_citizenship_required"] is None;assert analysis["clearance_required"] is None;assert semantic_rejection_reasons(analysis,PROFILE)==[]

def test_semantic_six_year_requirement_remains_eligible():
    jd="Requires 6 years of professional experience in data engineering.";assert semantic_rejection_reasons(_analysis(6,jd),PROFILE)==[]

def test_semantic_seven_year_requirement_is_rejected():
    jd="Requires 7 years of professional experience in data engineering.";reasons=semantic_rejection_reasons(_analysis(7,jd),PROFILE);assert any("exclusive ceiling 7" in r for r in reasons)
