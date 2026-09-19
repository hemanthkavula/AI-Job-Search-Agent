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
