from types import SimpleNamespace

from app.jd_coverage_plan import build_coverage_plan


def test_coverage_plan_does_not_import_legacy_profile_technology():
    job=SimpleNamespace(description="Build reliable Python and SQL data pipelines.")
    profile={
        "skills":["LEGACY_PROFILE_TECH"],
        "skill_categories":{"Legacy":["LEGACY_PROFILE_TECH"]},
        "experience":[{"environment":"LEGACY_PROFILE_TECH, ANOTHER_OLD_TOOL"}],
    }
    plan=build_coverage_plan(job,profile)
    serialized=str(plan)
    assert "LEGACY_PROFILE_TECH" not in serialized
    assert "ANOTHER_OLD_TOOL" not in serialized


def test_coverage_plan_is_invariant_to_profile_technical_content():
    job=SimpleNamespace(description="Hands-on experience with Databricks, Python, SQL, and Apache Spark is required.")
    clean=build_coverage_plan(job,{})
    noisy=build_coverage_plan(job,{
        "skills":["Snowflake","Kafka","Java"],
        "skill_categories":{"Cloud":["AWS Glue","Redshift"]},
        "experience":[{"environment":"Azure Data Factory, Synapse, Terraform"}],
    })
    assert noisy == clean


def test_resume_strategy_base_when_no_targets():
    from app.jd_coverage_plan import select_resume_strategy
    job=SimpleNamespace(description="Join our growing team.",description_complete=False)
    assert select_resume_strategy(job,{})["strategy"]=="BASE"


def test_resume_strategy_limited_when_partial_jd_has_targets():
    from app.jd_coverage_plan import select_resume_strategy
    job=SimpleNamespace(description="Build Python SQL Spark data pipelines.",description_complete=False)
    result=select_resume_strategy(job,{})
    assert result["coverage_plan"]["target_count"]>0
    assert result["strategy"]=="LIMITED"


def test_resume_strategy_full_when_complete_jd_has_targets():
    from app.jd_coverage_plan import select_resume_strategy
    job=SimpleNamespace(description="Build Python SQL Spark data pipelines.",description_complete=True)
    result=select_resume_strategy(job,{})
    assert result["coverage_plan"]["target_count"]>0
    assert result["strategy"]=="FULL"
