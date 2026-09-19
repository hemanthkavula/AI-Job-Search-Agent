from app.jd_finalizer import finalize_report
import json

def test_unresolved_ats_is_held_before_resume_generation(tmp_path, monkeypatch):
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"dice:test","source":"dice","company_key":"Example","title":"Senior Data Engineer","employment_type":"Full-Time","description":"placeholder"}}]}
    inp=tmp_path/"eligible.json"; out=tmp_path/"finalized.json"
    inp.write_text(json.dumps(report),encoding="utf-8")
    resolved={"external_id":"dice:test","source":"dice","company_key":"Example","title":"Senior Data Engineer","employment_type":"Full-Time","url":"https://www.dice.com/job-detail/test","original_url":"https://www.dice.com/job-detail/test","description":"Responsibilities requirements qualifications Python SQL Spark data pipelines production support. "+"x"*1300,"description_complete":True,"description_length":1400,"jd_signal_score":4,"ats_resolution":"unresolved"}
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:resolved)
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    result=finalize_report(str(inp),str(out))
    assert result["finalized"]==1
    assert result["results"][0]["job"]["application_route"]=="DICE"
    assert result["results"][0]["job"]["ats_provider"]=="dice"

def test_verified_ats_reaches_finalized_stage(tmp_path, monkeypatch):
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"lever:test","source":"lever","company_key":"Example","title":"Senior Data Engineer","employment_type":"Full-Time","description":"placeholder"}}]}
    inp=tmp_path/"eligible.json"; out=tmp_path/"finalized.json"
    inp.write_text(json.dumps(report),encoding="utf-8")
    resolved={"external_id":"lever:test","source":"lever","company_key":"Example","title":"Senior Data Engineer","employment_type":"Full-Time","description":"Responsibilities requirements qualifications Python SQL Spark data pipelines production support. "+"x"*1300,"description_complete":True,"description_length":1400,"jd_signal_score":4,"ats_resolution":"direct","ats_provider":"lever","original_url":"https://jobs.lever.co/example/test"}
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:resolved)
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    result=finalize_report(str(inp),str(out))
    assert result["finalized"]==1
    assert result["results"][0]["action"]=="FINAL_JD_VERIFIED"


def test_short_usable_dice_jd_uses_conservative_tailoring(tmp_path, monkeypatch):
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"dice:short","source":"dice","company_key":"Example","title":"Data Engineer","employment_type":"Full-Time","description":"placeholder"}}]}
    inp=tmp_path/"eligible_short.json"; out=tmp_path/"finalized_short.json"
    inp.write_text(json.dumps(report),encoding="utf-8")
    description="Requirements: Python, SQL, AWS Glue, S3 and ETL pipeline development. Experience building reliable cloud data pipelines and supporting production workloads. Qualifications include strong SQL and Python skills. "+"x"*120
    resolved={"external_id":"dice:short","source":"dice","company_key":"Example","title":"Data Engineer","employment_type":"Full-Time","url":"https://www.dice.com/job-detail/short","original_url":"https://www.dice.com/job-detail/short","description":description,"description_complete":False,"description_usable":True,"description_length":len(description),"jd_signal_score":2,"ats_resolution":"unresolved"}
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:resolved)
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    result=finalize_report(str(inp),str(out))
    assert result["finalized"]==1
    job=result["results"][0]["job"]
    assert job["tailoring_mode"]=="BASE_RESUME_CONSERVATIVE"
    assert job["application_route"]=="DICE"
