import app.ats_resolver as ats_resolver
import app.company_domain_resolver as domain_resolver
import app.company_registry as company_registry


def test_jobposting_hiring_organization_url_is_carried(monkeypatch):
    page='''<html><script type="application/ld+json">
    {"@type":"JobPosting","title":"Data Engineer",
     "hiringOrganization":{"@type":"Organization","name":"Example Corp",
     "sameAs":"https://www.example.com/"}}</script></html>'''
    monkeypatch.setattr(ats_resolver,"_fetch",lambda url:page)
    job={"company":"Example Corp","url":"https://board.example/jobs/1"}
    out=ats_resolver.resolve_original_ats(job)
    assert out["organization_url_evidence"]=="https://www.example.com/"


def test_company_registry_persists_jobposting_org_evidence():
    reg={}
    company_registry.learn_from_jobs([{
        "company":"Example Corp","source":"discovery",
        "url":"https://board.example/jobs/1",
        "organization_url_evidence":"https://www.example.com/"
    }],reg)
    row=reg[company_registry.company_key("Example Corp")]
    assert row["organization_url_evidence"]=="https://www.example.com/"
    assert row["organization_url_evidence_source"]=="jobposting_hiring_organization"


def test_jobposting_org_url_requires_first_party_verification(monkeypatch):
    calls=[]
    monkeypatch.setattr(domain_resolver,"_first_party_match",
                        lambda url,name,timeout=12: calls.append((url,name)) or None)
    monkeypatch.setattr(domain_resolver,"_verified_domain_from_search",lambda row:None)
    row={"company":"Example Corp","organization_url_evidence":"https://wrong.example/"}
    assert domain_resolver.resolve_company(row) is None
    assert calls==[("https://wrong.example/","Example Corp")]


def test_verified_jobposting_org_url_becomes_official_domain(monkeypatch):
    monkeypatch.setattr(domain_resolver,"_first_party_match",
                        lambda url,name,timeout=12:{
                            "official_domain":"example.com",
                            "official_url":"https://example.com",
                            "domain_evidence":"placeholder",
                        })
    row={"company":"Example Corp","organization_url_evidence":"https://example.com/"}
    out=domain_resolver.resolve_company(row)
    assert out["official_domain"]=="example.com"
    assert out["domain_evidence"]=="jobposting_hiring_organization_plus_first_party_identity"
