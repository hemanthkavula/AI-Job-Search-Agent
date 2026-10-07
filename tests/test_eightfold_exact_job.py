from app.sources import eightfold


def test_domain_from_entity_encoded_eightfold_shell():
    body='<div data-props="{&#34;domain&#34;: &#34;eaton.com&#34;, &#34;positionDetailsConfig&#34;: {}}"></div>'
    assert eightfold._domain_from_page(body,"https://eaton.eightfold.ai/careers/job/687239519334")=="eaton.com"


def test_fetch_job_uses_pcsx_position_details(monkeypatch):
    url="https://eaton.eightfold.ai/careers/job/687239519334"
    shell='<div data-props="{&#34;domain&#34;: &#34;eaton.com&#34;}"></div>'
    seen=[]
    monkeypatch.setattr(eightfold,"_get",lambda value,timeout=25:shell)

    def fake_json(value,timeout=25,referer=""):
        seen.append((value,referer))
        if "/api/pcsx/position_details?" in value:
            return {
                "data":{
                    "position":{
                        "id":687239519334,
                        "name":"Lead AI and Data Engineer",
                        "location":"Beachwood, OH, United States",
                        "atsJobId":"JR-1001",
                        "employmentType":"Full time",
                        "jobDescription":"<p>Responsibilities: design, develop, and deploy scalable AI and data engineering solutions.</p><p>Requirements: Python, SQL, Azure OpenAI, Databricks, MLOps, CI/CD, testing, and production support.</p>",
                    }
                }
            }
        raise AssertionError("fallback endpoint should not be needed")

    monkeypatch.setattr(eightfold,"_get_json",fake_json)
    row=eightfold.fetch_job("Eaton",url)
    assert row["company_key"]=="Eaton"
    assert row["title"]=="Lead AI and Data Engineer"
    assert row["job_id"]=="687239519334"
    assert row["requisition_id"]=="JR-1001"
    assert row["location"]=="Beachwood, OH, United States"
    assert "Azure OpenAI" in row["description"]
    assert row["original_url"]==url
    assert seen[0][0].startswith("https://eaton.eightfold.ai/api/pcsx/position_details?")
    assert "position_id=687239519334" in seen[0][0]
    assert "domain=eaton.com" in seen[0][0]
    assert seen[0][1]==url


def test_fetch_job_falls_back_to_classic_detail(monkeypatch):
    url="https://tenant.eightfold.ai/careers/job/12345"
    monkeypatch.setattr(eightfold,"_get",lambda value,timeout=25:'<div data-x="{&#34;domain&#34;: &#34;tenant.com&#34;}"></div>')
    calls=[]
    def fake_json(value,timeout=25,referer=""):
        calls.append(value)
        if "/api/pcsx/position_details?" in value:
            return None
        if "/api/apply/v2/jobs/12345?" in value:
            return {
                "id":12345,
                "posting_name":"Data Engineer",
                "display_job_id":"REQ-9",
                "job_description":"Responsibilities build reliable data pipelines. Requirements Python SQL Spark cloud data engineering and production support.",
            }
        return None
    monkeypatch.setattr(eightfold,"_get_json",fake_json)
    row=eightfold.fetch_job("Tenant",url)
    assert row["title"]=="Data Engineer"
    assert row["requisition_id"]=="REQ-9"
    assert any("/api/apply/v2/jobs/12345?" in call for call in calls)



def test_fetch_job_handles_slugged_numeric_position_segment(monkeypatch):
    url="https://tenant.eightfold.ai/careers/job/12345-data-engineer"
    monkeypatch.setattr(eightfold,"_get",lambda value,timeout=25:'<div data-x="{&#34;domain&#34;: &#34;tenant.com&#34;}"></div>')
    seen=[]
    def fake_json(value,timeout=25,referer=""):
        seen.append(value)
        if "/api/pcsx/position_details?" in value:
            return {"data":{"position":{
                "id":12345,
                "name":"Data Engineer",
                "jobDescription":"Responsibilities build data pipelines. Requirements Python SQL Spark cloud ETL and production support.",
            }}}
        return None
    monkeypatch.setattr(eightfold,"_get_json",fake_json)
    row=eightfold.fetch_job("Tenant",url)
    assert row["job_id"]=="12345"
    assert "position_id=12345" in seen[0]
