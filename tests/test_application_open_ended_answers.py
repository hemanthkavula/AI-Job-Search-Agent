from app.application_autofill import _question_answer
from tests.test_application_profile_mapping import ITEM
from tests.test_application_technical_answers import _profile


def test_pipeline_answer_uses_profile_evidence():
    p=_profile()
    answer=_question_answer("Briefly describe a data pipeline you built.",ITEM,p)
    assert answer=="Built PySpark pipelines on Databricks and AWS Glue using SQL."
    assert "Databricks" in answer
    assert "AWS Glue" in answer


def test_interest_answer_uses_only_profile_and_jd_overlap():
    p=_profile()
    item=dict(ITEM,title="Senior Data Engineer",
              description="Build scalable Databricks and Python pipelines on AWS.")
    answer=_question_answer("Why are you interested in this role?",item,p)
    assert "Senior Data Engineer" in answer
    assert "Python" in answer
    assert "Databricks" in answer
    assert "COBOL" not in answer


def test_about_yourself_uses_explicit_summary():
    p=_profile()
    p["summary_source"]=["Data engineer with five years of experience.","Experienced with cloud data pipelines."]
    answer=_question_answer("Tell us about yourself.",ITEM,p)
    assert answer=="Data engineer with five years of experience. Experienced with cloud data pipelines."


def test_unknown_open_ended_question_remains_unanswered():
    assert _question_answer("What is your favorite book and why?",ITEM,_profile()) is None
