from app.sources.smartrecruiters import _is_de_title


def test_smartrecruiters_prefilter_is_recall_first_for_de_family():
    assert _is_de_title("Senior Data Engineer")
    assert _is_de_title("Data Platform Lead")
    assert _is_de_title("Data Infrastructure Developer")
    assert _is_de_title("Cloud Data Pipeline Specialist")
    assert _is_de_title("Enterprise Data Warehouse Developer")
    assert _is_de_title("Analytics Engineer")
    assert _is_de_title("ETL Engineer")
    assert not _is_de_title("Software Engineer")
    assert not _is_de_title("Data Scientist")
    assert not _is_de_title("Business Analyst")
