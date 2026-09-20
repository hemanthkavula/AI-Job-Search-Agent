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
