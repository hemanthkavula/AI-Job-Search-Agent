from app.filters import title_is_target


def test_career_site_recall_gate_covers_broad_data_engineering_family():
    # Career-site discovery is intentionally broad and no longer owns a private
    # _de_candidate prefilter. Validate the centralized classifier that receives
    # those discovered postings instead.
    assert title_is_target("Senior Data Engineer")
    assert title_is_target("Staff Research Data Engineering - Platform")
    assert title_is_target("Senior Data Platform Engineer")
    assert title_is_target("Data Infrastructure Engineer")
    assert title_is_target("Enterprise Data Warehouse Engineer")
    assert title_is_target("Cloud Data Integration Engineer")
    assert title_is_target("Analytics Engineer")
    assert title_is_target("ETL Engineer")
    assert title_is_target("Research Data & ML Platform Engineering", "Build Spark data pipelines and Kafka ingestion for a lakehouse platform.")
    assert not title_is_target("Software Engineer")
    assert not title_is_target("Data Scientist")
    assert not title_is_target("Business Analyst")
