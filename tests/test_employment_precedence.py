from app.filters import employment_is_target, passes_hard_filters


PROFILE={
    "preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"max_required_years":7},
    "work_authorization":{"requires_sponsorship_now":False,"requires_sponsorship_future":False},
    "candidate_experience_years":5,
}


def test_trusted_full_time_metadata_ignores_unrelated_part_time_footer():
    description=(
        "Build ETL/ELT data pipelines with Python, SQL, Spark, Kafka, Databricks, "
        "data modeling and data warehouse systems. "
        "Position & Application Details Full-Time Regular Positions: this is a "
        "full-time, regular position working 40 standard weekly hours. "
        "Related links: Enrollment Counselor; Evaluator; "
        "Field Experience Roles (Part-time & Intermittent); Program Mentor."
    )
    assert employment_is_target("Full time",description)


def test_wgu_run_271_regression_reaches_hard_filter_eligibility():
    description=(
        "Develops and builds ETL/ELT data pipelines for use in data analysis. "
        "Creates and maintains optimal data pipeline architecture. Uses Python, "
        "SQL, Spark, Kafka, Databricks, data modeling and data warehouse systems. "
        "Minimum Qualifications: 4 years of experience in Data Engineering. "
        "Position & Application Details Full-Time Regular Positions: this is a "
        "full-time, regular position classified for 40 standard weekly hours. "
        "Field Experience Roles (Part-time & Intermittent) Program Mentor."
    )
    ok,reasons=passes_hard_filters({
        "title":"Data Engineer II",
        "company":"Western Governors University",
        "location":"Salt Lake City, UT",
        "employment_type":"Full time",
        "description":description,
    },PROFILE)
    assert ok,reasons


def test_explicit_contract_role_still_rejected_even_with_full_time_metadata():
    assert not employment_is_target(
        "Full-Time",
        "This is a 6 month contract position supporting a migration project.",
    )


def test_explicit_part_time_role_still_rejected_even_with_full_time_metadata():
    assert not employment_is_target(
        "Full-Time",
        "This position is a part-time role requiring 20 hours per week.",
    )
