from app import provider_adapter_router as router


def test_detected_eightfold_routes_to_dedicated_collector(monkeypatch):
    seen={}
    def fake(company,url):
        seen.update(company=company,url=url)
        return [{"title":"Lead AI and Data Engineer","url":url,"description":"full jd"}]
    monkeypatch.setattr(router,"eightfold_jobs",fake)
    url="https://eaton.eightfold.ai/careers/job/123"
    rows,provider,identifier=router.fetch_provider_jobs(
        None,"Eaton",{"original_url":url}
    )
    assert provider=="eightfold"
    assert identifier=="eaton"
    assert seen=={"company":"Eaton","url":"https://eaton.eightfold.ai/careers"}
    assert rows[0]["title"]=="Lead AI and Data Engineer"


def test_detected_greenhouse_routes_to_greenhouse_api(monkeypatch):
    seen={}
    def fake(token):
        seen["token"]=token
        return [{"title":"Senior Data Engineer","url":"https://boards.greenhouse.io/acme/jobs/1"}]
    monkeypatch.setattr(router,"greenhouse_jobs",fake)
    rows,provider,identifier=router.fetch_provider_jobs(
        None,"Acme",{"original_url":"https://boards.greenhouse.io/acme/jobs/1"}
    )
    assert provider=="greenhouse"
    assert identifier=="acme"
    assert seen["token"]=="acme"
    assert rows


def test_unknown_supported_long_tail_uses_generic_public_ats(monkeypatch):
    seen={}
    def fake(company,url,provider,pattern):
        seen.update(company=company,url=url,provider=provider,pattern=pattern)
        return [{"title":"Data Engineer","url":url}]
    monkeypatch.setattr(router,"public_ats_jobs",fake)
    url="https://acme.breezy.hr/p/abc-data-engineer"
    rows,provider,identifier=router.fetch_provider_jobs(
        None,"Acme",{"original_url":url}
    )
    assert provider=="breezyhr"
    assert seen["provider"]=="breezyhr"
    assert rows


def test_workday_detected_source_uses_tenant_site(monkeypatch):
    seen={}
    def fake(company,host,tenant,site,locale="en-US",hours=48):
        seen.update(company=company,host=host,tenant=tenant,site=site,locale=locale,hours=hours)
        return [{"title":"Data Engineer","url":"https://example.test/job/1"}]
    monkeypatch.setattr(router,"workday_jobs",fake)
    url="https://eaton.wd5.myworkdayjobs.com/en-US/Eaton_Careers/job/Test/Data-Engineer_123"
    rows,provider,identifier=router.fetch_provider_jobs(None,"Eaton",{"original_url":url},hours=24)
    assert provider=="workday"
    assert identifier=="eaton|Eaton_Careers"
    assert seen["tenant"]=="eaton"
    assert seen["site"]=="Eaton_Careers"
    assert seen["hours"]==24
    assert rows



def test_fetch_exact_job_uses_provider_native_eightfold_detail_api(monkeypatch):
    url="https://tenant.eightfold.ai/careers/job/abc123"
    exact={
        "company_key":"Eaton",
        "title":"Lead AI and Data Engineer",
        "job_id":"abc123",
        "requisition_id":"REQ-123",
        "location":"Beachwood, OH",
        "description":"Responsibilities build enterprise AI and data engineering solutions with Azure OpenAI.",
        "url":url,
        "original_url":url,
    }
    seen={}
    def fake(company,value,timeout=25):
        seen.update(company=company,url=value,timeout=timeout)
        return exact
    monkeypatch.setattr(router,"eightfold_job",fake)
    row,provider,identifier=router.fetch_exact_job(None,"Eaton",{"original_url":url})
    assert provider=="eightfold"
    assert identifier=="tenant"
    assert seen=={"company":"Eaton","url":url,"timeout":25}
    assert row["title"]=="Lead AI and Data Engineer"
    assert row["job_id"]=="abc123"
    assert row["location"]=="Beachwood, OH"
    assert "Azure OpenAI" in row["description"]


def test_board_fallback_normalizes_generic_detail_url(monkeypatch):
    seen={}
    def fake(company,url):
        seen.update(company=company,url=url)
        return []
    monkeypatch.setattr(router,"eightfold_jobs",fake)
    url="https://tenant.eightfold.ai/careers/job/abc123"
    router.fetch_provider_jobs(None,"Eaton",{"original_url":url})
    assert seen["url"]=="https://tenant.eightfold.ai/careers"



def test_fetch_exact_job_prefers_provider_native_exact_fetcher(monkeypatch):
    url="https://tenant.eightfold.ai/careers/job/12345"
    seen={}
    def fake(company,job_url,timeout=25):
        seen.update(company=company,url=job_url,timeout=timeout)
        return {
            "title":"Lead AI and Data Engineer",
            "company_key":"Eaton",
            "url":url,
            "original_url":url,
            "job_id":"12345",
            "requisition_id":"12345",
            "description":"Responsibilities build scalable AI and data engineering solutions. Requirements Python SQL Databricks Azure OpenAI machine learning deployment monitoring CI/CD production support.",
            "location":"Beachwood, OH",
            "exact_job_metadata_source":"eightfold_public_api",
        }
    monkeypatch.setattr(router,"eightfold_job",fake)
    row,provider,identifier=router.fetch_exact_job(None,"Eaton",{"original_url":url})
    assert provider=="eightfold"
    assert identifier=="tenant"
    assert seen["company"]=="Eaton"
    assert seen["url"]==url
    assert row["title"]=="Lead AI and Data Engineer"
    assert row["exact_job_metadata_source"]=="eightfold_public_api"



def test_fetch_exact_job_uses_provider_native_oracle_detail_api(monkeypatch):
    url="https://efds.fa.em5.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/72173"
    seen={}
    def fake(company,value,timeout=25):
        seen.update(company=company,url=value,timeout=timeout)
        return {
            "title":"Software Validation Engineer",
            "company_key":"Ford",
            "url":url,
            "original_url":url,
            "job_id":"72173",
            "requisition_id":"72173",
            "description":"Description: validate embedded software and vehicle systems. Responsibilities: develop validation plans, execute automated and manual testing, investigate defects, and collaborate with engineering teams. Qualifications: engineering degree, software validation experience, Python, test automation, and systems knowledge. " * 3,
            "description_complete":True,
            "exact_job_metadata_source":"oracle_exact_api",
        }
    monkeypatch.setattr(router,"oracle_job",fake)
    row,provider,identifier=router.fetch_exact_job(None,"Ford",{"original_url":url})
    assert provider=="oracle"
    assert seen=={"company":"Ford","url":url,"timeout":25}
    assert row["title"]=="Software Validation Engineer"
    assert row["requisition_id"]=="72173"
    assert row["description_complete"] is True
    assert row["exact_job_metadata_source"]=="oracle_exact_api"
