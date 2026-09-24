from app.jd_finalizer import finalize_report
import json

def test_unresolved_ats_is_held_before_resume_generation(tmp_path, monkeypatch):
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"dice:test","source":"dice","company_key":"Example","title":"Senior Data Engineer","location":"Jersey City, NJ, United States","employment_type":"Full-Time","description":"placeholder"}}]}
    inp=tmp_path/"eligible.json"; out=tmp_path/"finalized.json"
    inp.write_text(json.dumps(report),encoding="utf-8")
    resolved={"external_id":"dice:test","source":"dice","company_key":"Example","title":"Senior Data Engineer","employment_type":"Full-Time","url":"https://www.dice.com/job-detail/test","original_url":"https://www.dice.com/job-detail/test","description":"Responsibilities requirements qualifications Python SQL Spark data pipelines production support. "+"x"*1300,"description_complete":True,"description_length":1400,"jd_signal_score":4,"ats_resolution":"unresolved"}
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:resolved)
    monkeypatch.setattr("app.jd_finalizer._live_public_job_page",lambda url:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.job_detail_is_live",lambda *args,**kwargs:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    result=finalize_report(str(inp),str(out))
    assert result["finalized"]==1
    assert result["results"][0]["job"]["application_route"]=="DICE"
    assert result["results"][0]["job"]["ats_provider"]=="dice"

def test_verified_ats_reaches_finalized_stage(tmp_path, monkeypatch):
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"lever:test","source":"lever","company_key":"Example","title":"Senior Data Engineer","location":"Jersey City, NJ, United States","employment_type":"Full-Time","description":"placeholder"}}]}
    inp=tmp_path/"eligible.json"; out=tmp_path/"finalized.json"
    inp.write_text(json.dumps(report),encoding="utf-8")
    resolved={"external_id":"lever:test","source":"lever","company_key":"Example","title":"Senior Data Engineer","location":"Jersey City, NJ, United States","employment_type":"Full-Time","description":"Responsibilities requirements qualifications Python SQL Spark data pipelines production support. "+"x"*1300,"description_complete":True,"description_length":1400,"jd_signal_score":4,"ats_resolution":"direct","ats_provider":"lever","original_url":"https://jobs.lever.co/example/test"}
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:resolved)
    monkeypatch.setattr("app.jd_finalizer._live_public_job_page",lambda url:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.job_detail_is_live",lambda *args,**kwargs:(True,"test_live"))
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
    monkeypatch.setattr("app.jd_finalizer._live_public_job_page",lambda url:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.job_detail_is_live",lambda *args,**kwargs:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    result=finalize_report(str(inp),str(out))
    assert result["finalized"]==1
    job=result["results"][0]["job"]
    assert job["tailoring_mode"]=="BASE_RESUME_CONSERVATIVE"
    assert job["application_route"]=="DICE"


def test_mckesson_explicit_no_future_immigration_support_is_rejected(tmp_path, monkeypatch):
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"mckesson:test","source":"workday","company_key":"McKesson","title":"Data Engineer","description":"placeholder"}}]}
    inp=tmp_path/"mckesson.json"; out=tmp_path/"mckesson_out.json"; inp.write_text(json.dumps(report),encoding="utf-8")
    description=("Requirements: Python SQL data pipelines. Applicants must be currently authorized to work in the United States on a fulltime basis without the need for employer support or sponsorship now or in the future. This includes F1 OPT, F1 STEM OPT and H1B. McKesson does not provide employer support or sponsorship for any immigration related employment benefit. "+"x"*1200)
    resolved={"external_id":"mckesson:test","source":"workday","company_key":"McKesson","title":"Data Engineer","employment_type":"Full-Time","description":description,"description_complete":True,"description_length":len(description),"jd_signal_score":3,"ats_provider":"workday","original_url":"https://example.com/job"}
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:resolved)
    monkeypatch.setattr("app.jd_finalizer._live_public_job_page",lambda url:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.job_detail_is_live",lambda *args,**kwargs:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer"],"min_required_years":4,"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    result=finalize_report(str(inp),str(out))
    assert result["finalized"]==0
    assert result["rejections"][0]["eligibility"]["sponsorship"]["category"]=="NO_SPONSORSHIP"


def test_caci_degree_plus_15_years_is_rejected(tmp_path, monkeypatch):
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"caci:test","source":"career_site","company_key":"CACI International","title":"Data Engineer","description":"placeholder"}}]}
    inp=tmp_path/"caci.json"; out=tmp_path/"caci_out.json"; inp.write_text(json.dumps(report),encoding="utf-8")
    description=("Qualifications: Bachelor's degree + 15 years of experience in data engineering, data architecture, software engineering, or related field; equivalencies considered (Master's + 12 years; 21 years with no degree; AA + 17 years). Responsibilities include Python SQL and data pipelines. "+"x"*1200)
    resolved={"external_id":"caci:test","source":"career_site","company_key":"CACI International","title":"Data Engineer","employment_type":"Full-Time","description":description,"description_complete":True,"description_length":len(description),"jd_signal_score":3,"ats_provider":"icims","original_url":"https://example.com/job"}
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:resolved)
    monkeypatch.setattr("app.jd_finalizer._live_public_job_page",lambda url:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.job_detail_is_live",lambda *args,**kwargs:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer"],"min_required_years":4,"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    result=finalize_report(str(inp),str(out))
    assert result["finalized"]==0
    assert result["rejections"][0]["eligibility"]["experience"]["category"]=="EXPERIENCE_TOO_SENIOR"
    assert result["rejections"][0]["eligibility"]["experience"]["required_years"]>=12
