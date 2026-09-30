from app.filters import title_is_target


def test_smartrecruiters_defers_job_family_to_central_classifier():
    # SmartRecruiters now collects all fresh/unknown-date postings and deliberately
    # has no source-local _is_de_title gate. Test the centralized qualification
    # behavior rather than restoring the obsolete source restriction.
    assert title_is_target("Senior Data Engineer")
    assert title_is_target("Staff Research Data Engineering - Platform")
    assert title_is_target("Senior Data Platform Engineer")
    assert title_is_target("Data Infrastructure Engineer")
    assert title_is_target("Cloud Data Pipeline Engineer")
    assert title_is_target("Enterprise Data Warehouse Engineer")
    assert title_is_target("Analytics Engineer")
    assert title_is_target("ETL Engineer")
    assert title_is_target("Research Data & ML Platform Engineering", "Build Spark data pipelines, Kafka ingestion and lakehouse infrastructure.")
    assert not title_is_target("Software Engineer")
    assert not title_is_target("Data Scientist")
    assert not title_is_target("Business Analyst")
