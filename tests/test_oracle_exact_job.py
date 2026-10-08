import json

from app.sources import oracle


def test_oracle_exact_job_uses_full_external_requisition_fields(monkeypatch):
    url="https://efds.fa.em5.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/72173"
    seen=[]

    monkeypatch.setattr(
        oracle,
        "_page_config",
        lambda base_url,timeout: ("1001","https://efds.fa.em5.oraclecloud.com"),
    )

    payload={
        "RequisitionId":72173,
        "Title":"Software Validation Engineer",
        "PrimaryLocation":"Dearborn, Michigan, United States",
        "WorkerType":"Regular",
        "ExternalPostedStartDate":"2026-10-01T00:00:00Z",
        "ShortDescriptionStr":"Help validate production vehicle software.",
        "ExternalDescriptionStr":"Build and execute robust software validation strategies across embedded and vehicle systems. Work with developers and systems engineers to identify risk, reproduce failures, and improve release quality. "*2,
        "ExternalResponsibilitiesStr":"Create validation plans and automated tests, execute bench and vehicle testing, triage defects, analyze logs, document results, and drive issues to closure with cross-functional engineering partners. "*2,
        "ExternalQualificationsStr":"Bachelor's degree in engineering or computer science, software validation experience, Python or similar scripting, test automation, debugging, and strong systems thinking. "*2,
    }

    def fake_get(request_url,timeout=20):
        seen.append(request_url)
        return json.dumps(payload)

    monkeypatch.setattr(oracle,"_get",fake_get)
    row=oracle.fetch_job("Ford",url,timeout=25)

    assert row is not None
    assert row["title"]=="Software Validation Engineer"
    assert row["company_key"]=="Ford"
    assert row["location"]=="Dearborn, Michigan, United States"
    assert row["requisition_id"]=="72173"
    assert row["description_complete"] is True
    assert len(row["description"])>500
    assert "Responsibilities:" in row["description"]
    assert "Qualifications:" in row["description"]
    assert row["exact_job_metadata_source"]=="oracle_exact_api"
    assert any(
        "/recruitingCEJobRequisitionDetailsPreviews/72173?onlyData=true" in request_url
        for request_url in seen
    )


def test_oracle_exact_job_rejects_short_search_only_payload(monkeypatch):
    url="https://tenant.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/123"
    monkeypatch.setattr(
        oracle,
        "_page_config",
        lambda base_url,timeout: ("22","https://tenant.fa.oraclecloud.com"),
    )
    monkeypatch.setattr(
        oracle,
        "_get",
        lambda request_url,timeout=20: json.dumps({
            "RequisitionId":123,
            "Title":"Data Engineer",
            "ShortDescriptionStr":"Short search summary only.",
        }),
    )
    assert oracle.fetch_job("Acme",url) is None
