from app import jd_finalizer


def test_resolution_queries_use_requisition_location_and_verified_domain(monkeypatch):
    job={
        "company":"Example Health",
        "company_key":"Example Health",
        "title":"Senior Data Engineer",
        "location":"Chicago, IL",
        "requisition_id":"REQ-4242",
        "organization_url_evidence":"https://examplehealth.com",
    }
    monkeypatch.setattr(jd_finalizer,"resolve_company",lambda row,allow_name_search=False:{
        "official_domain":"examplehealth.com","official_url":"https://examplehealth.com"
    })
    seen=[]
    monkeypatch.setattr(jd_finalizer,"_fetch_public_page",lambda url: seen.append(url) or "")
    assert jd_finalizer._resolve_employer_career_page(job)==("","")
    decoded="\n".join(__import__("urllib.parse",fromlist=["unquote"]).unquote(x) for x in seen)
    assert "site:examplehealth.com" in decoded
    assert "REQ-4242" in decoded
    assert "Chicago" in decoded
