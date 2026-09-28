from app.ats_audit import _domain_coherence_violations


def test_domain_coherence_accepts_matching_business_contexts():
    rows={
        "Fidelity Investments":["Built Spark pipelines for market data and trading analytics."],
        "Cigna Healthcare":["Built claims and eligibility pipelines with Databricks."],
        "Target Corporation":["Built Kafka pipelines for POS and inventory data."],
    }
    assert _domain_coherence_violations(rows)==[]


def test_domain_coherence_rejects_cross_employer_business_context():
    rows={
        "Fidelity Investments":["Built HIPAA claims pipelines with Spark."],
        "Cigna Healthcare":[],
        "Target Corporation":[],
    }
    findings=_domain_coherence_violations(rows)
    assert findings
    assert findings[0]["company"]=="Fidelity Investments"
    assert findings[0]["conflicting_domain"]=="healthcare"


def test_neutral_de_technology_is_not_a_domain_violation():
    rows={
        "Fidelity Investments":["Built Databricks and Kafka ingestion pipelines."],
        "Cigna Healthcare":["Developed SQL and Airflow ETL workflows."],
        "Target Corporation":["Engineered Spark lakehouse transformations."],
    }
    assert _domain_coherence_violations(rows)==[]
