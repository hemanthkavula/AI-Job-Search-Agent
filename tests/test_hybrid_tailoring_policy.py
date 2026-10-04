from types import SimpleNamespace

from app.ats_audit import _new_metric_findings, _retained_master_counts
from app.jd_coverage_plan import build_coverage_plan
from app.master_resume import load_master_resume
from app.resume_tailoring_policy import (
    MODE_FULL,
    MODE_LIGHT,
    MODE_MASTER,
    MODE_MODERATE,
    MODE_STRONG,
    determine_tailoring_policy,
)


def _job(description, **extra):
    return SimpleNamespace(
        company="Example",
        title="Senior Data Engineer",
        description=description,
        description_complete=extra.get("description_complete", True),
        description_usable=True,
        tailoring_mode=extra.get("tailoring_mode", "FULL_JD"),
    )


def test_zero_targets_use_unchanged_master_mode():
    job=_job("General data engineering role.")
    policy=determine_tailoring_policy(job,{"target_count":0,"requirements":[]})
    assert policy["mode"]==MODE_MASTER
    assert policy["minimum_master_bullets_retained"]=={
        "Fidelity Investments":10,"Cigna Healthcare":8,"Target Corporation":8
    }


def test_five_keyword_short_jd_is_light_hybrid_not_full_rewrite():
    job=_job("Required: Java, Python, SQL, Airflow, and Databricks.")
    plan={
        "target_count":5,
        "requirements":[{"term":x,"classification":"required"} for x in ("Java","Python","SQL","Airflow","Databricks")],
    }
    policy=determine_tailoring_policy(job,plan)
    assert policy["mode"]==MODE_LIGHT
    assert policy["minimum_master_bullets_retained"]["Fidelity Investments"]==7
    assert policy["minimum_master_bullets_retained"]["Cigna Healthcare"]==6
    assert policy["minimum_master_bullets_retained"]["Target Corporation"]==6


def test_detailed_five_target_jd_is_moderate_hybrid():
    responsibilities=" ".join([
        "Design production data pipelines and define technical requirements.",
        "Build reusable ingestion workflows and transformation layers.",
        "Develop reliable orchestration and production support processes.",
        "Implement data quality controls and integration testing.",
        "Optimize pipeline performance and troubleshoot production workloads.",
        "Partner with engineering stakeholders and document design decisions.",
    ])
    filler=" Data engineering responsibilities include scalable architecture, observability, governance, reliability, testing, deployment, documentation, and stakeholder collaboration."
    job=_job(("Required technologies are Java, Python, SQL, Airflow, and Databricks. "+responsibilities+filler*6))
    plan={
        "target_count":5,
        "requirements":[{"term":x,"classification":"required"} for x in ("Java","Python","SQL","Airflow","Databricks")],
    }
    policy=determine_tailoring_policy(job,plan)
    assert policy["mode"]==MODE_MODERATE


def test_rich_eight_target_jd_is_strong_hybrid():
    text=("Design build develop implement engineer orchestrate ingest transform optimize and support enterprise data pipelines. "*12)
    job=_job(text)
    plan={"target_count":8,"requirements":[{"term":f"T{i}","classification":"material"} for i in range(8)]}
    assert determine_tailoring_policy(job,plan)["mode"]==MODE_STRONG


def test_rich_large_target_jd_can_be_full_hybrid():
    text=("Design build develop implement engineer orchestrate ingest transform optimize and support enterprise data pipelines. "*20)
    job=_job(text)
    plan={"target_count":12,"requirements":[{"term":f"T{i}","classification":"material"} for i in range(12)]}
    assert determine_tailoring_policy(job,plan)["mode"]==MODE_FULL


def test_partial_jd_stays_light_even_with_many_targets():
    job=_job(
        "Python SQL Java Airflow Databricks Snowflake Kafka Spark dbt Terraform are listed.",
        description_complete=False,
        tailoring_mode="BASE_RESUME_CONSERVATIVE",
    )
    plan={"target_count":10,"requirements":[]}
    assert determine_tailoring_policy(job,plan)["mode"]==MODE_LIGHT


def test_java_and_python_are_both_kept_when_both_are_explicit_jd_targets():
    job=_job("Required hands-on experience with Java, Python, SQL, Airflow, and Databricks.")
    plan=build_coverage_plan(job,{"skills":[],"skill_categories":{},"experience":[]})
    assert "Java" in plan["targeted_terms"]
    assert "Python" in plan["targeted_terms"]
    assert "SQL" in plan["targeted_terms"]
    assert "Airflow" in plan["targeted_terms"]
    assert "Databricks" in plan["targeted_terms"]


def test_verbatim_master_metrics_are_allowed_but_modified_metric_claims_are_not():
    master=load_master_resume()
    by_company={row["company"]:list(row["bullets"]) for row in master["experience"]}
    assert _new_metric_findings(by_company,master,False)==[]

    fidelity=list(by_company["Fidelity Investments"])
    fidelity[0]=fidelity[0]+" Improved throughput by 99%."
    findings=_new_metric_findings({**by_company,"Fidelity Investments":fidelity},master,False)
    assert findings
    assert findings[0]["company"]=="Fidelity Investments"


def test_master_retention_counts_exact_unchanged_bullets():
    master=load_master_resume()
    by_company={row["company"]:list(row["bullets"]) for row in master["experience"]}
    counts=_retained_master_counts(by_company,master)
    assert counts=={"Fidelity Investments":10,"Cigna Healthcare":8,"Target Corporation":8}

    by_company["Target Corporation"][0]="Rewritten Target bullet without copying the master sentence."
    counts=_retained_master_counts(by_company,master)
    assert counts["Target Corporation"]==7
