from app.filters import passes_hard_filters

PROFILE={
  "preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"max_required_years":7},
  "work_authorization":{"requires_sponsorship_future":True},
  "candidate_experience_years":5
}

def test_data_engineer_passes():
    ok,_=passes_hard_filters({"title":"Senior Data Engineer","location":"Jersey City, NJ, United States","description":"Python AWS"},PROFILE)
    assert ok

def test_no_sponsorship_rejected():
    ok,r=passes_hard_filters({"title":"Senior Data Engineer","description":"Candidates must be eligible to work in the US without visa sponsorship."},PROFILE)
    assert not ok and any("sponsorship" in x.lower() for x in r)

def test_excess_years_rejected():
    ok,r=passes_hard_filters({"title":"Senior Data Engineer","description":"10+ years of professional experience required."},PROFILE)
    assert not ok and any("10" in x for x in r)

def test_experience_within_range_passes():
    ok,_=passes_hard_filters({"title":"Senior Data Engineer","location":"Jersey City, NJ, United States","description":"5+ years of professional experience required."},PROFILE)
    assert ok

def test_sponsorship_unknown_is_not_rejected():
    ok,_=passes_hard_filters({"title":"Data Engineer","location":"Jersey City, NJ, United States","description":"Python SQL Spark"},PROFILE)
    assert ok


def test_contract_third_party_rejected():
    ok,r=passes_hard_filters({
      "title":"Senior Azure Data Engineer - Elasticsearch",
      "employment_type":"Contract, Third Party",
      "description":"Python Databricks SQL Elasticsearch Kafka Azure"
    },PROFILE)
    assert not ok and any("employment type" in x.lower() for x in r)

def test_min_experience_wording_rejected():
    ok,r=passes_hard_filters({
      "title":"Senior Azure Data Engineer - Elasticsearch",
      "employment_type":"Full-Time",
      "description":"Required Experience / Skills: Experience Min 10+ years of software engineering experience."
    },PROFILE)
    assert not ok and any("10" in x for x in r)

def test_peoplen_tech_regression_rejected_for_both_reasons():
    ok,r=passes_hard_filters({
      "title":"Senior Azure Data Engineer - Elasticsearch",
      "employment_type":"Contract, Third Party",
      "description":"Required Experience / Skills: Experience Min 10+ years of software engineering experience. Python Databricks SQL Elasticsearch Kafka Azure."
    },PROFILE)
    assert not ok
    assert any("employment type" in x.lower() for x in r)
    assert any("10" in x for x in r)


def test_india_location_rejected():
    ok,r=passes_hard_filters({
      "title":"Senior Data Engineer",
      "location":"Bengaluru, Karnataka, India",
      "employment_type":"Full-Time",
      "description":"Python SQL Spark Databricks"
    },PROFILE)
    assert not ok and any("location outside United States" in x for x in r)

def test_us_location_passes():
    ok,r=passes_hard_filters({
      "title":"Senior Data Engineer",
      "location":"Jersey City, NJ, United States",
      "employment_type":"Full-Time",
      "description":"Python SQL Spark Databricks"
    },PROFILE)
    assert ok

def test_foreign_jd_location_rejected_when_location_missing():
    ok,r=passes_hard_filters({
      "title":"Data Engineer",
      "location":"",
      "employment_type":"Full-Time",
      "description":"Position based in Hyderabad, India. Python SQL Spark."
    },PROFILE)
    assert not ok and any("location outside United States" in x for x in r)


def test_account_executive_not_promoted_by_de_keywords():
    ok,r=passes_hard_filters({
      "title":"Enterprise Account Executive, Dept. of Transportation",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Databricks Spark data pipelines data warehouse lakehouse data integration security governance."
    },PROFILE)
    assert not ok and any("job family" in x.lower() for x in r)

def test_solutions_engineer_not_promoted_by_de_keywords():
    ok,r=passes_hard_filters({
      "title":"Sr. Solutions Engineer - Digital Native Business",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Python SQL Databricks Spark ETL data pipelines data warehouse Kafka."
    },PROFILE)
    assert not ok and any("job family" in x.lower() for x in r)

def test_platform_manager_not_promoted_by_de_keywords():
    ok,r=passes_hard_filters({
      "title":"Senior Platform Manager, Data Products, Finance Accounting",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Spark Databricks data pipelines ETL data modeling data integration lakehouse."
    },PROFILE)
    assert not ok and any("job family" in x.lower() for x in r)

def test_data_platform_engineer_remains_target():
    ok,_=passes_hard_filters({
      "title":"Senior Data Platform Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Build Spark and Databricks data pipelines."
    },PROFILE)
    assert ok


def test_sdet_not_promoted_by_de_keywords():
    ok,r=passes_hard_filters({
      "title":"Sr. Software Development Engineer in Test, AI/ML",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Python Docker Jenkins Git Kubernetes GCP Spark data pipelines ETL data warehouse."
    },PROFILE)
    assert not ok and any("job family" in x.lower() for x in r)

def test_data_solutions_specialist_not_promoted_by_de_keywords():
    ok,r=passes_hard_filters({
      "title":"Data Solutions & Validation Sr. Specialist",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Python SQL Spark data governance data quality data modeling ETL data pipelines."
    },PROFILE)
    assert not ok and any("job family" in x.lower() for x in r)

def test_etl_engineer_is_explicit_adjacent_target():
    ok,_=passes_hard_filters({
      "title":"Senior ETL Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Build enterprise ETL pipelines using SQL and Python."
    },PROFILE)
    assert ok

def test_unknown_title_not_promoted_by_many_de_keywords():
    ok,r=passes_hard_filters({
      "title":"Technical Delivery Specialist",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Python SQL Spark Databricks Kafka ETL data pipelines data warehouse lakehouse data modeling."
    },PROFILE)
    assert not ok and any("job family" in x.lower() for x in r)

def test_junior_data_engineer_explicit_exclusion_wins():
    ok,r=passes_hard_filters({
      "title":"Junior Data Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Python SQL Spark."
    },PROFILE)
    assert not ok and any("job family" in x.lower() for x in r)
