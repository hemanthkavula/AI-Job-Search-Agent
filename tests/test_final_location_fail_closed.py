import json
from datetime import datetime, timezone
from app import jd_finalizer

def _base_job():
    return {
        "external_id":"dice:1","source":"dice","company_key":"Example Inc",
        "title":"Senior Data Engineer","location":"","employment_type":"Full-time",
        "description":"Build data pipelines with Spark, Kafka, ETL and data warehouse systems. Responsibilities and qualifications included.",
        "description_complete":True,"url":"https://jobs.example.com/job/1",
        "original_url":"https://jobs.example.com/job/1","aggregator_url":"https://www.dice.com/job-detail/1",
        "ats_provider":"lever"
    }

def test_resolved_aggregator_blank_location_fails_closed(monkeypatch,tmp_path):
    report=tmp_path/"eligible.json";out=tmp_path/"final.json"
    report.write_text(json.dumps({"results":[{"action":"ELIGIBLE_FOR_RESUME","job":_base_job()}]}))
    monkeypatch.setattr(jd_finalizer,"load_profile",lambda:{"preferences":{"target_roles":["Data Engineer"],"max_required_years":8},"work_authorization":{"requires_sponsorship_future":True},"candidate_experience_years":5})
    monkeypatch.setattr(jd_finalizer,"resolve_full_jd",lambda job:dict(job))
    monkeypatch.setattr(jd_finalizer,"_fetch_public_page",lambda url:"")
    monkeypatch.setattr(jd_finalizer,"_official_job_location",lambda page,job:"")
    monkeypatch.setattr(jd_finalizer,"_official_posted_at",lambda page,now=None:(now,"today"))
    monkeypatch.setattr(jd_finalizer,"_live_public_job_page",lambda url:(True,"reachable"))
    result=jd_finalizer.finalize_report(str(report),str(out),now=datetime(2026,9,29,14,0,tzinfo=timezone.utc))
    assert result["finalized"]==0
    assert any("geography unverified" in " ".join(x.get("reasons") or []) for x in result["rejections"])
