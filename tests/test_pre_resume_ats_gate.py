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
    assert result["finalized"]==0
    assert result["held_or_rejected"]==1
    assert result["rejections"][0]["action"]=="HOLD_ATS_UNRESOLVED"

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
    assert result["held_or_rejected"]==0
    assert result["results"][0]["action"]=="FINAL_JD_VERIFIED"
    assert result["results"][0]["job"]["application_route"]=="EXTERNAL_ATS"


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
    assert result["finalized"]==0
    assert result["held_or_rejected"]==1
    assert result["rejections"][0]["action"]=="HOLD_ATS_UNRESOLVED"


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


def test_direct_workday_relative_posting_is_rechecked_at_finalization(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"workday:R120623","source":"workday","company_key":"Samsung Austin Semiconductor","title":"Senior Data Engineer","description":"placeholder"}}]}
    inp=tmp_path/"samsung_stale.json"; out=tmp_path/"samsung_stale_out.json"
    inp.write_text(json.dumps(report),encoding="utf-8")
    description="Responsibilities: build data pipelines. Requirements: Python SQL Spark. Qualifications: data engineering experience. "+"x"*1300
    resolved={"external_id":"workday:R120623","source":"workday","company_key":"Samsung Austin Semiconductor","title":"Senior Data Engineer","employment_type":"Full-Time","description":description,"description_complete":True,"description_length":len(description),"jd_signal_score":3,"ats_provider":"workday","original_url":"https://sec.wd3.myworkdayjobs.com/en-US/Samsung_Careers/job/Austin-TX/Senior-Data-Engineer_R120623","posted_on":"Posted 4 Days Ago"}
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:resolved)
    monkeypatch.setattr("app.jd_finalizer._live_public_job_page",lambda url:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.job_detail_is_live",lambda *args,**kwargs:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    now=datetime(2026,9,28,12,0,tzinfo=timezone.utc)
    result=finalize_report(str(inp),str(out),hours=61,now=now)
    assert result["finalized"]==0
    assert result["held_or_rejected"]==1
    rejection=result["rejections"][0]
    assert rejection["action"]=="REJECT_STALE_OFFICIAL_POSTING"
    assert rejection["diagnostics"]["official_posted_label"]=="Posted 4 Days Ago"


def test_direct_workday_one_day_relative_posting_remains_fresh(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"workday:fresh","source":"workday","company_key":"Example","title":"Senior Data Engineer","description":"placeholder"}}]}
    inp=tmp_path/"workday_fresh.json"; out=tmp_path/"workday_fresh_out.json"
    inp.write_text(json.dumps(report),encoding="utf-8")
    description="Responsibilities: build data pipelines. Requirements: Python SQL Spark. Qualifications: data engineering experience. "+"x"*1300
    resolved={"external_id":"workday:fresh","source":"workday","company_key":"Example","title":"Senior Data Engineer","location":"Austin, TX, United States","employment_type":"Full-Time","description":description,"description_complete":True,"description_length":len(description),"jd_signal_score":3,"ats_provider":"workday","original_url":"https://example.com/job","posted_on":"Posted 1 Day Ago"}
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:resolved)
    monkeypatch.setattr("app.jd_finalizer._live_public_job_page",lambda url:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.job_detail_is_live",lambda *args,**kwargs:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    now=datetime(2026,9,28,12,0,tzinfo=timezone.utc)
    result=finalize_report(str(inp),str(out),hours=61,now=now)
    assert result["finalized"]==1
    assert result["held_or_rejected"]==0


def test_official_ats_foreign_location_overrides_false_us_discovery_location(tmp_path, monkeypatch):
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"smartrecruiters:bosch","source":"smartrecruiters","company_key":"Bosch Group","title":"Sr.Data Engineering","location":"United States","description":"placeholder"}}]}
    inp=tmp_path/"bosch_location.json"; out=tmp_path/"bosch_location_out.json"
    inp.write_text(json.dumps(report),encoding="utf-8")
    description="Responsibilities: build data pipelines with Python SQL Spark. Requirements: data engineering experience. Qualifications: 6-8 years relevant experience. "+"x"*1300
    url="https://jobs.smartrecruiters.com/BoschGroup/example"
    resolved={"external_id":"smartrecruiters:bosch","source":"smartrecruiters","company_key":"Bosch Group","company":"Bosch Group","title":"Sr.Data Engineering","location":"United States","employment_type":"Full-Time","description":description,"description_complete":True,"description_length":len(description),"jd_signal_score":3,"ats_provider":"smartrecruiters","original_url":url}
    page='''<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"Sr.Data Engineering","hiringOrganization":{"@type":"Organization","name":"Bosch Group"},"jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","streetAddress":"no.123 industrial layout hosur road koramangala","addressLocality":"bengaluru","postalCode":"560095","addressCountry":"India"}},"description":"Responsibilities requirements qualifications data pipelines Python SQL Spark"}</script>'''
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:resolved)
    monkeypatch.setattr("app.jd_finalizer._fetch_public_page",lambda target:page)
    monkeypatch.setattr("app.jd_finalizer._live_public_job_page",lambda target:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":6})
    result=finalize_report(str(inp),str(out))
    assert result["finalized"]==0
    assert result["held_or_rejected"]==1
    rejection=result["rejections"][0]
    assert rejection["action"]=="SKIP_FINAL_ELIGIBILITY"
    assert any(reason.startswith("location outside United States target") for reason in rejection["reasons"])
    assert rejection["job"]["official_location"].endswith("bengaluru, 560095, India")
    assert rejection["job"]["discovery_location"]=="United States"


def test_remote_job_uses_applicant_location_requirements(monkeypatch,tmp_path):
    inp=tmp_path/"eligible.json";out=tmp_path/"finalized.json"
    description="Responsibilities: build data pipelines with Python SQL Spark. Requirements: data engineering experience. Qualifications: 5 years relevant experience. "+"x"*1300
    url="https://jobs.example.com/remote-role"
    raw={"external_id":"lever:remote","source":"lever","company_key":"Example","company":"Example","title":"Senior Data Engineer","location":"Remote","employment_type":"Full-time","description":description,"description_complete":True,"original_url":url}
    inp.write_text(json.dumps({"results":[{"action":"ELIGIBLE_FOR_RESUME","job":raw}]}),encoding="utf-8")
    page='''<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"Senior Data Engineer","hiringOrganization":{"name":"Example"},"jobLocationType":"TELECOMMUTE","applicantLocationRequirements":{"@type":"Country","name":"India"},"description":"Responsibilities requirements qualifications data pipelines Python SQL Spark"}</script>'''
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:dict(raw))
    monkeypatch.setattr("app.jd_finalizer._fetch_public_page",lambda target:page)
    monkeypatch.setattr("app.jd_finalizer._live_public_job_page",lambda *args,**kwargs:(True,"reachable"))
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"min_required_years":4,"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    result=finalize_report(str(inp),str(out))
    assert result["finalized"]==0
    assert result["held_or_rejected"]==1
    held=result["rejections"][0]
    assert held["job"]["official_location"]=="Remote - India"
    assert "location outside United States target" in held["reason"]


def test_aggregator_us_location_cannot_survive_unlocated_official_page(tmp_path, monkeypatch):
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":{"external_id":"dice:foreign","source":"dice","company_key":"Example Corp","title":"Data Engineer","location":"United States","description":"placeholder"}}]}
    inp=tmp_path/"aggregator_location.json"; out=tmp_path/"aggregator_location_out.json"
    inp.write_text(json.dumps(report),encoding="utf-8")
    description=("Responsibilities: build data pipelines with Python SQL Spark. Requirements: data engineering experience. Qualifications: 5 years relevant experience. "+"x"*1300)
    resolved={"external_id":"dice:foreign","source":"dice","company_key":"Example Corp","company":"Example Corp","title":"Data Engineer","location":"United States","employment_type":"Full-Time","description":description,"description_complete":True,"description_length":len(description),"jd_signal_score":3,"ats_provider":"greenhouse","original_url":"https://boards.greenhouse.io/example/jobs/123","aggregator_url":"https://www.dice.com/job-detail/abc","posted_at":"2026-09-29T12:00:00Z"}
    monkeypatch.setattr("app.jd_finalizer.resolve_full_jd",lambda job:resolved)
    monkeypatch.setattr("app.jd_finalizer._fetch_public_page",lambda target:"<html><body>Responsibilities requirements qualifications data pipelines Python SQL Spark</body></html>")
    monkeypatch.setattr("app.jd_finalizer._official_posted_at",lambda page,now=None:(now,"today"))
    monkeypatch.setattr("app.jd_finalizer._live_public_job_page",lambda target:(True,"test_live"))
    monkeypatch.setattr("app.jd_finalizer.load_profile",lambda:{"preferences":{"target_roles":["Data Engineer"],"min_required_years":4,"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    result=finalize_report(str(inp),str(out))
    assert result["finalized"]==0
    assert result["rejections"][0]["action"]=="SKIP_FINAL_ELIGIBILITY"
    assert any(reason.startswith("location outside United States target") for reason in result["rejections"][0]["reasons"])
