from types import SimpleNamespace

from app.scoring import analyze_job


PROFILE = {
    "skills": ["Python", "SQL", "Apache Spark", "Snowflake"],
    "priority_skills": ["Python", "SQL", "Apache Spark", "Snowflake"],
    "preferences": {
        "employment_types": ["Full-Time", "W2"],
        "preferred_locations": ["New Jersey", "New York", "Pennsylvania"],
        "target_roles": ["Data Engineer", "Senior Data Engineer"],
    },
}


def test_analytics_engineer_with_de_jd_gets_target_role_score():
    job = SimpleNamespace(
        company="Example",
        title="Analytics Engineer",
        description="Build data pipelines and ETL workflows using Snowflake, SQL, Python and Spark for warehouse data modeling.",
        location="Seattle, WA",
        employment_type="Full-Time",
    )
    result = analyze_job(job, PROFILE)
    assert result["reasons"][0] == "Role relevance: target/adjacent data engineering role"


def test_any_us_location_gets_full_location_contribution():
    job = SimpleNamespace(
        company="Example",
        title="Data Engineer",
        description="Build data pipelines with Python and SQL.",
        location="Austin, TX",
        employment_type="Full-Time",
    )
    result = analyze_job(job, PROFILE)
    assert "Location fit contribution: 10/10" in result["reasons"]
