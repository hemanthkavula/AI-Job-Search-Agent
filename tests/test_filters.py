from app.filters import passes_hard_filters, employment_is_target, title_is_target

PROFILE={
  "preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"min_required_years":3,"max_required_years":7},
  "work_authorization":{"requires_sponsorship_future":True},
  "candidate_experience_years":5
}

def test_data_engineer_passes():
    ok,_=passes_hard_filters({"title":"Senior Data Engineer","location":"Jersey City, NJ, United States","description":"Python AWS"},PROFILE)
    assert ok

def test_data_engineer_phrase_anywhere_in_long_title_is_target():
    titles=(
      "Senior Cloud Data Engineer - AWS / Spark / Databricks",
      "Vice President, Enterprise Risk Lead Data Engineer II - Regulatory Platform",
      "2026 Technology - Data Engineer, Global Markets Data Platform (Hybrid)",
      "Principal Engineer - Data Engineer / Snowflake / Kafka",
      "Data Engineer III - Finance, Risk, Compliance and Market Data",
    )
    for title in titles:
        assert title_is_target(title, ""), title

def test_data_engineering_phrase_anywhere_in_long_title_is_target():
    assert title_is_target("Senior Engineer - Data Engineering, Cloud Lakehouse", "")

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



def test_excluded_prior_employers_are_hard_rejected():
    from app.filters import employer_is_excluded
    for name in ("Fidelity Investments","Fidelity","Cigna Healthcare","The Cigna Group","Target Corporation","Target"):
        assert employer_is_excluded(name) is True
    assert employer_is_excluded("Capital One") is False


def test_unknown_ats_employment_metadata_does_not_false_reject_full_time_role():
    assert employment_is_target("Experienced", "NYC, Full-Time: Experienced. Build reliable data pipelines.")

def test_unknown_employment_metadata_still_rejects_explicit_contract():
    assert not employment_is_target("Experienced", "This is a 6 month contract position.")


def test_analytics_engineer_with_strong_de_jd_is_target():
    ok,_=passes_hard_filters({
      "title":"Senior Analytics Engineer - Data",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Build data pipelines and ETL with dbt, Spark, Snowflake, Airflow, data modeling and data warehouse systems."
    },PROFILE)
    assert ok

def test_analytics_engineer_without_de_evidence_is_not_target():
    ok,_=passes_hard_filters({
      "title":"Adobe Analytics Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Own Adobe Analytics tagging, dashboards and marketing reporting."
    },PROFILE)
    assert not ok

def test_software_engineer_data_platform_with_strong_de_jd_is_target():
    ok,_=passes_hard_filters({
      "title":"Software Engineer, Data Platform",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Build Spark data pipelines, Kafka ingestion, lakehouse storage, Airflow orchestration and data warehouse integrations."
    },PROFILE)
    assert ok


def test_excess_years_working_in_data_engineering_rejected():
    ok,r=passes_hard_filters({
      "title":"Lead Data Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"10+ years working in data engineering, including at least 3 years in a leadership role."
    },PROFILE)
    assert not ok and any("10" in x for x in r)

def test_excess_years_in_data_engineering_rejected():
    ok,r=passes_hard_filters({
      "title":"Lead Data Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Minimum qualifications include 10+ years in data engineering and strong SQL skills."
    },PROFILE)
    assert not ok and any("10" in x for x in r)

def test_excess_years_building_data_platforms_rejected():
    ok,r=passes_hard_filters({
      "title":"Lead Data Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"8+ years building enterprise data platforms, pipelines, and distributed data systems."
    },PROFILE)
    assert not ok and any("8" in x for x in r)


def test_neutral_immigration_benefit_language_does_not_imply_no_sponsorship():
    ok,_=passes_hard_filters({
      "title":"Data Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Questions about an immigration related employment benefit may be directed to Human Resources. Build Python SQL Spark pipelines."
    },PROFILE)
    assert ok


def test_explicit_no_future_employer_support_remains_rejected():
    ok,r=passes_hard_filters({
      "title":"Data Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Applicants must be authorized to work without the need for employer support or sponsorship now or in the future."
    },PROFILE)
    assert not ok and any("sponsorship" in x.lower() for x in r)


def test_us_citizenship_requirement_is_rejected():
    ok,r=passes_hard_filters({
      "title":"Data Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"U.S. citizenship is required. Build Spark and SQL pipelines."
    },PROFILE)
    assert not ok and any("citizenship" in x.lower() for x in r)


def test_security_clearance_requirement_is_rejected():
    ok,r=passes_hard_filters({
      "title":"Data Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Candidate must have a Secret clearance. Build Spark and SQL pipelines."
    },PROFILE)
    assert not ok and any("clearance" in x.lower() for x in r)


def test_generic_remote_official_ats_lead_survives_discovery_for_final_verification():
    ok,_=passes_hard_filters({
      "title":"Data Engineer",
      "source":"greenhouse",
      "location":"Remote",
      "employment_type":"Full-Time",
      "description":"Build Spark SQL ETL data pipelines."
    },PROFILE)
    assert ok


def test_blank_location_official_ats_lead_survives_discovery_for_final_verification():
    ok,_=passes_hard_filters({
      "title":"Data Engineer",
      "source":"lever",
      "location":"",
      "employment_type":"Full-Time",
      "description":"Build Spark SQL ETL data pipelines."
    },PROFILE)
    assert ok


def test_generic_remote_with_explicit_foreign_jd_location_is_rejected():
    ok,r=passes_hard_filters({
      "title":"Data Engineer",
      "source":"greenhouse",
      "location":"Remote",
      "employment_type":"Full-Time",
      "description":"Remote role based in Bengaluru, India. Build Spark SQL ETL data pipelines."
    },PROFILE)
    assert not ok and any("location outside United States" in x for x in r)


def test_positive_future_immigration_sponsorship_language_is_not_rejected():
    ok,reasons=passes_hard_filters({
      "title":"Data Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"We provide immigration support or sponsorship now or in the future for qualified candidates. Build Python SQL Spark data pipelines."
    },PROFILE)
    assert ok, reasons


def test_explicit_no_future_sponsorship_still_rejected_after_positive_language_fix():
    ok,reasons=passes_hard_filters({
      "title":"Data Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"We cannot provide current or future sponsorship. Build Python SQL Spark data pipelines."
    },PROFILE)
    assert not ok
    assert any("sponsorship" in reason.lower() for reason in reasons)


def test_sponsorship_silence_does_not_reject_eligible_job():
    ok,reasons=passes_hard_filters({
      "title":"Senior Data Engineer",
      "location":"United States",
      "employment_type":"Full-Time",
      "description":"Design and build Python, SQL, Spark, Kafka and cloud data pipelines. Requires 5+ years of data engineering experience."
    },PROFILE)
    assert ok, reasons
    assert not any("sponsorship" in reason.lower() for reason in reasons)


def test_two_plus_year_posting_is_rejected_by_hard_window():
    ok,reasons=passes_hard_filters({
      "title":"Data Engineer","location":"United States","employment_type":"Full-Time",
      "description":"Requires 2+ years of professional experience building Python SQL Spark data pipelines."
    },PROFILE)
    assert not ok
    assert any("experience requirement" in reason.lower() and "2" in reason for reason in reasons)

def test_three_plus_year_posting_is_eligible_boundary():
    ok,reasons=passes_hard_filters({
      "title":"Data Engineer","location":"United States","employment_type":"Full-Time",
      "description":"Requires 3+ years of professional experience building Python SQL Spark data pipelines."
    },PROFILE)
    assert ok,reasons

def test_seven_plus_year_posting_is_eligible_boundary():
    ok,reasons=passes_hard_filters({
      "title":"Senior Data Engineer","location":"United States","employment_type":"Full-Time",
      "description":"Requires 7+ years of professional experience building Python SQL Spark data pipelines."
    },PROFILE)
    assert ok,reasons

def test_eight_plus_year_posting_is_rejected_by_hard_window():
    ok,reasons=passes_hard_filters({
      "title":"Senior Data Engineer","location":"United States","employment_type":"Full-Time",
      "description":"Requires 8+ years of professional experience building Python SQL Spark data pipelines."
    },PROFILE)
    assert not ok
    assert any("experience requirement" in reason.lower() and "8" in reason for reason in reasons)
