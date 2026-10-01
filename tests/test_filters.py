from app.filters import passes_hard_filters, employment_is_target, title_is_target

PROFILE={"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"min_required_years":3,"max_required_years":7},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5}

def _job(description,title="Data Engineer",location="United States",employment_type="Full-Time"):
    return {"title":title,"location":location,"employment_type":employment_type,"description":description}

def test_data_engineer_passes():
    ok,_=passes_hard_filters(_job("Python AWS Spark data pipelines",title="Senior Data Engineer",location="Jersey City, NJ, United States"),PROFILE);assert ok

def test_data_engineer_phrase_anywhere_in_long_title_is_target():
    titles=("Senior Cloud Data Engineer - AWS / Spark / Databricks","Vice President, Enterprise Risk Lead Data Engineer II - Regulatory Platform","2026 Technology - Data Engineer, Global Markets Data Platform (Hybrid)","Principal Engineer - Data Engineer / Snowflake / Kafka","Data Engineer III - Finance, Risk, Compliance and Market Data","Staff Research Data Engineering - Platform & Infrastructure","Principal Cloud Data Platform Engineering - Risk & Research","Senior Engineer, Data Products & Analytics Engineering")
    for title in titles: assert title_is_target(title,"Spark Kafka data pipelines lakehouse"),title

def test_data_engineering_phrase_anywhere_in_long_title_is_target(): assert title_is_target("Senior Engineer - Data Engineering, Cloud Lakehouse","")
def test_no_sponsorship_rejected():
    ok,r=passes_hard_filters(_job("Candidates must be eligible to work in the US without visa sponsorship.",title="Senior Data Engineer"),PROFILE);assert not ok and any("sponsorship" in x.lower() for x in r)
def test_excess_years_rejected():
    ok,r=passes_hard_filters(_job("10+ years of professional experience required.",title="Senior Data Engineer"),PROFILE);assert not ok and any("10" in x for x in r)
def test_experience_within_range_passes():
    ok,_=passes_hard_filters(_job("5+ years of professional experience required.",title="Senior Data Engineer"),PROFILE);assert ok
def test_sponsorship_unknown_is_not_rejected():
    ok,_=passes_hard_filters(_job("Python SQL Spark"),PROFILE);assert ok
def test_contract_third_party_rejected():
    ok,r=passes_hard_filters(_job("Python Databricks SQL Elasticsearch Kafka Azure",title="Senior Azure Data Engineer - Elasticsearch",employment_type="Contract, Third Party"),PROFILE);assert not ok and any("employment type" in x.lower() for x in r)
def test_india_location_rejected():
    ok,r=passes_hard_filters(_job("Python SQL Spark Databricks",title="Senior Data Engineer",location="Bengaluru, Karnataka, India"),PROFILE);assert not ok and any("location outside United States" in x for x in r)
def test_us_location_passes():
    ok,_=passes_hard_filters(_job("Python SQL Spark Databricks",title="Senior Data Engineer",location="Jersey City, NJ, United States"),PROFILE);assert ok
def test_account_executive_not_promoted_by_de_keywords():
    ok,r=passes_hard_filters(_job("Databricks Spark data pipelines data warehouse lakehouse data integration security governance.",title="Enterprise Account Executive, Dept. of Transportation"),PROFILE);assert not ok and any("job family" in x.lower() for x in r)
def test_data_platform_engineer_remains_target():
    ok,_=passes_hard_filters(_job("Build Spark and Databricks data pipelines.",title="Senior Data Platform Engineer"),PROFILE);assert ok
def test_unknown_ats_employment_metadata_does_not_false_reject_full_time_role(): assert employment_is_target("Experienced","NYC, Full-Time: Experienced. Build reliable data pipelines.")
def test_unknown_employment_metadata_still_rejects_explicit_contract(): assert not employment_is_target("Experienced","This is a 6 month contract position.")
def test_explicit_analytics_engineer_title_is_target_even_when_discovery_jd_is_thin():
    ok,_=passes_hard_filters(_job("Own Adobe Analytics tagging, dashboards and marketing reporting.",title="Adobe Analytics Engineer"),PROFILE);assert ok
def test_software_engineer_data_platform_with_strong_de_jd_is_target():
    ok,_=passes_hard_filters(_job("Build Spark data pipelines, Kafka ingestion, lakehouse storage, Airflow orchestration and data warehouse integrations.",title="Software Engineer, Data Platform"),PROFILE);assert ok
def test_unrelated_data_analyst_is_not_target(): assert not title_is_target("Senior Data Analyst","Build dashboards, reporting and business metrics.")
def test_unrelated_data_scientist_is_not_target(): assert not title_is_target("Senior Data Scientist","Build forecasting models and statistical experiments.")
def test_generic_software_engineer_without_data_context_is_not_target(): assert not title_is_target("Senior Software Engineer","Build APIs and web services in Java.")
def test_neutral_immigration_benefit_language_does_not_imply_no_sponsorship():
    ok,_=passes_hard_filters(_job("Questions about an immigration related employment benefit may be directed to Human Resources. Build Python SQL Spark pipelines."),PROFILE);assert ok
def test_explicit_no_future_employer_support_remains_rejected():
    ok,r=passes_hard_filters(_job("Applicants must be authorized to work without the need for employer support or sponsorship now or in the future."),PROFILE);assert not ok and any("sponsorship" in x.lower() for x in r)
def test_us_citizenship_requirement_is_rejected():
    ok,r=passes_hard_filters(_job("U.S. citizenship is required. Build Spark and SQL pipelines."),PROFILE);assert not ok and any("citizenship" in x.lower() for x in r)
def test_security_clearance_requirement_is_rejected():
    ok,r=passes_hard_filters(_job("Candidate must have a Secret clearance. Build Spark and SQL pipelines."),PROFILE);assert not ok and any("clearance" in x.lower() for x in r)
def test_positive_future_immigration_sponsorship_language_is_not_rejected():
    ok,reasons=passes_hard_filters(_job("We provide immigration support or sponsorship now or in the future for qualified candidates. Build Python SQL Spark data pipelines."),PROFILE);assert ok,reasons
def test_sponsorship_silence_does_not_reject_eligible_job():
    ok,reasons=passes_hard_filters(_job("Design and build Python, SQL, Spark, Kafka and cloud data pipelines. Requires 5+ years of data engineering experience.",title="Senior Data Engineer"),PROFILE);assert ok,reasons
def test_two_plus_year_posting_is_rejected_by_hard_window():
    ok,reasons=passes_hard_filters(_job("Requires 2+ years of professional experience building Python SQL Spark data pipelines."),PROFILE);assert not ok and any("2" in r for r in reasons)
def test_three_plus_year_posting_is_eligible_boundary():
    ok,reasons=passes_hard_filters(_job("Requires 3+ years of professional experience building Python SQL Spark data pipelines."),PROFILE);assert ok,reasons
def test_six_plus_year_posting_is_eligible_upper_boundary():
    ok,reasons=passes_hard_filters(_job("Requires 6+ years of professional experience building Python SQL Spark data pipelines.",title="Senior Data Engineer"),PROFILE);assert ok,reasons
def test_seven_plus_year_posting_is_rejected_by_exclusive_ceiling():
    ok,reasons=passes_hard_filters(_job("Requires 7+ years of professional experience building Python SQL Spark data pipelines.",title="Senior Data Engineer"),PROFILE);assert not ok and any("7" in r for r in reasons)
def test_eight_plus_year_posting_is_rejected_by_hard_window():
    ok,reasons=passes_hard_filters(_job("Requires 8+ years of professional experience building Python SQL Spark data pipelines.",title="Senior Data Engineer"),PROFILE);assert not ok and any("8" in r for r in reasons)
