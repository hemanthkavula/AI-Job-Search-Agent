import json
from app import jd_finalizer


def test_verified_long_tail_ats_is_finalized_for_manual_application(monkeypatch,tmp_path):
    report=tmp_path/"eligible.json"
    output=tmp_path/"finalized.json"
    job={
        "external_id":"manatal:1","source":"manatal","company_key":"Example Staffing",
        "title":"Data Engineer","location":"United States","employment_type":"Full-Time",
        "url":"https://example.careers-page.com/jobs/1","original_url":"https://example.careers-page.com/jobs/1",
        "ats_provider":"manatal","description":"Responsibilities " + ("build data pipelines Python SQL. "*80),
        "description_complete":True,
    }
    report.write_text(json.dumps({"results":[{"action":"ELIGIBLE_FOR_RESUME","job":job}]}),encoding="utf-8")
    monkeypatch.setattr(jd_finalizer,"load_profile",lambda:{})
    monkeypatch.setattr(jd_finalizer,"resolve_full_jd",lambda j:j)
    monkeypatch.setattr(jd_finalizer,"_live_public_job_page",lambda url:(True,"reachable"))
    monkeypatch.setattr(jd_finalizer,"two_category_filter",lambda j,p:{"eligible":True})
    monkeypatch.setattr(jd_finalizer,"passes_hard_filters",lambda j,p:(True,[]))
    result=jd_finalizer.finalize_report(str(report),str(output))
    assert result["finalized"]==1
    raw=result["results"][0]["job"]
    assert raw["application_route"]=="MANUAL_VERIFIED_ATS"
    assert raw["manual_application_required"] is True
