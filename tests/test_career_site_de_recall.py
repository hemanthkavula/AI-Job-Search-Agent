from app.sources.career_site import _de_candidate


def test_career_site_recall_gate_covers_broad_data_engineering_family():
    assert _de_candidate("Senior Data Engineer")
    assert _de_candidate("Data Platform Lead")
    assert _de_candidate("Data Infrastructure Developer")
    assert _de_candidate("Enterprise Data Warehouse Developer")
    assert _de_candidate("Cloud Data Integration Specialist")
    assert _de_candidate("Analytics Engineer")
    assert _de_candidate("ETL Engineer")
    assert not _de_candidate("Software Engineer")
    assert not _de_candidate("Data Scientist")
    assert not _de_candidate("Business Analyst")
