from app.application_autofill import _question_answer
from tests.test_application_profile_mapping import PROFILE, ITEM


def _profile():
    p=dict(PROFILE)
    p["candidate_experience_years"]=5
    p["skills"]=["Python","SQL","PySpark","Databricks","AWS Glue","Snowflake"]
    p["skill_categories"]={"Big Data":["Apache Spark","Kafka"]}
    p["experience"]=[{
        "title":"Senior Data Engineer",
        "company":"Example",
        "environment":"Python, PySpark, Databricks, AWS",
        "evidence":["Built PySpark pipelines on Databricks and AWS Glue using SQL."],
    }]
    return p


def test_supported_technical_yes_no_is_answered():
    p=_profile()
    assert _question_answer("Do you have experience with Databricks?",ITEM,p)=="Yes"
    assert _question_answer("Are you proficient with Python and SQL?",ITEM,p)=="Yes"


def test_unsupported_technology_is_left_unanswered():
    assert _question_answer("Do you have experience with COBOL?",ITEM,_profile()) is None


def test_technology_specific_years_are_not_invented():
    p=_profile()
    assert _question_answer("How many years of Databricks experience do you have?",ITEM,p) is None
    assert _question_answer("How many years of Python experience do you have?",ITEM,p) is None


def test_open_ended_technical_question_is_left_for_evidence_writer():
    p=_profile()
    assert _question_answer("Describe a complex Databricks pipeline you designed.",ITEM,p) is None
