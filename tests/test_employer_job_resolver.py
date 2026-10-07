import json

from app import company_registry, employer_job_resolver
from app.sources import dice


def test_company_registry_removes_aggregator_source_pollution(tmp_path):
    path=tmp_path/"company_registry.json"
    path.write_text(json.dumps({
        "techneptune consulting inc":{
            "company":"TECHNEPTUNE CONSULTING INC",
            "careers_url":"https://www.dice.com/job-detail/abc",
            "organization_url_evidence":"https://www.dice.com/company-profile/123",
            "domain_candidate_url":"https://www.dice.com/company-profile/123",
            "domain_candidate_host":"dice.com",
            "domain_candidate_evidence":"jobposting_hiring_organization",
        }
    }),encoding="utf-8")
    reg=company_registry.load(path)
    row=reg["techneptune consulting inc"]
    assert "careers_url" not in row
    assert "organization_url_evidence" not in row
    assert "domain_candidate_url" not in row
    assert row["aggregator_company_url"].startswith("https://www.dice.com/")


def test_dice_preserves_direct_employer_apply_metadata():
    row={
        "id":"123","companyName":"Example Co","title":"Senior Data Engineer",
        "detailsPageUrl":"https://www.dice.com/job-detail/123",
        "externalApplyUrl":"https://boards.greenhouse.io/example/jobs/456",
        "positionId":"REQ-456","postedDate":"2026-10-07T13:00:00Z",
        "description":"Responsibilities: build data pipelines with Python SQL Spark."
    }
    job=dice._normalize(row)
    assert job["url"]=="https://www.dice.com/job-detail/123"
    assert job["original_url"]=="https://boards.greenhouse.io/example/jobs/456"
    assert job["aggregator_url"]=="https://www.dice.com/job-detail/123"
    assert job["requisition_id"]=="REQ-456"


def test_verified_source_registry_resolves_exact_employer_job(monkeypatch):
    monkeypatch.setattr(employer_job_resolver,"load_company_registry",lambda:{})
    monkeypatch.setattr(employer_job_resolver,"load_registry",lambda:{
        "greenhouse":[{
            "company":"Example Health",
            "identifier":"examplehealth",
            "search_url":"https://boards.greenhouse.io/examplehealth",
        }]
    })
    monkeypatch.setattr(employer_job_resolver,"resolve_ats_tenant",lambda company:None)
    monkeypatch.setattr(employer_job_resolver,"greenhouse_jobs",lambda token:[
        {
            "title":"Senior Data Engineer",
            "location":"New York, NY",
            "url":"https://boards.greenhouse.io/examplehealth/jobs/999",
            "original_url":"https://boards.greenhouse.io/examplehealth/jobs/999",
            "description":"Responsibilities and qualifications for Python SQL Spark data pipelines.",
            "requisition_id":"REQ-999",
        },
        {
            "title":"Data Analyst",
            "location":"New York, NY",
            "url":"https://boards.greenhouse.io/examplehealth/jobs/111",
            "description":"analytics",
        },
    ])
    monkeypatch.setattr(employer_job_resolver,"save_registry",lambda reg:None)
    monkeypatch.setattr(employer_job_resolver,"save_company_registry",lambda reg:None)

    job={
        "source":"dice","company_key":"Example Health","title":"Senior Data Engineer",
        "location":"New York, NY","requisition_id":"REQ-999",
        "url":"https://www.dice.com/job-detail/abc",
    }
    resolved=employer_job_resolver.resolve(job)
    assert resolved is not None
    assert resolved["url"].endswith("/999")
    assert resolved["ats_provider"]=="greenhouse"
    assert resolved["ats_resolution"]=="verified_employer_source_match"


def test_ambiguous_same_title_board_is_not_silently_resolved(monkeypatch):
    monkeypatch.setattr(employer_job_resolver,"load_company_registry",lambda:{})
    monkeypatch.setattr(employer_job_resolver,"load_registry",lambda:{
        "greenhouse":[{
            "company":"Example Health",
            "identifier":"examplehealth",
            "search_url":"https://boards.greenhouse.io/examplehealth",
        }]
    })
    monkeypatch.setattr(employer_job_resolver,"resolve_ats_tenant",lambda company:None)
    monkeypatch.setattr(employer_job_resolver,"greenhouse_jobs",lambda token:[
        {"title":"Senior Data Engineer","location":"New York, NY","url":"https://boards.greenhouse.io/examplehealth/jobs/1","description":"Python SQL pipelines"},
        {"title":"Senior Data Engineer","location":"New York, NY","url":"https://boards.greenhouse.io/examplehealth/jobs/2","description":"Python SQL pipelines"},
    ])
    job={"source":"dice","company_key":"Example Health","title":"Senior Data Engineer","location":"New York, NY","url":"https://www.dice.com/job-detail/abc"}
    assert employer_job_resolver.resolve(job) is None
