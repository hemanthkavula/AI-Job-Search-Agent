from app.sources import oracle


def test_oracle_page_config_supports_legacy_data_attributes(monkeypatch):
    body = '<div data-sitenumber="CX_1001" data-apibaseurl="https://acme.fa.us2.oraclecloud.com/hcmRestApi/CandidateExperience/"></div>'
    monkeypatch.setattr(oracle, "_get", lambda url, timeout=20: body)
    site, api = oracle._page_config("https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX", 5)
    assert site == "CX_1001"
    assert api == "https://acme.fa.us2.oraclecloud.com"


def test_oracle_page_config_supports_embedded_json(monkeypatch):
    body = '{"siteNumber":"CX_2002","apiBaseUrl":"https://acme.fa.us2.oraclecloud.com/hcmRestApi/CandidateExperience/"}'
    monkeypatch.setattr(oracle, "_get", lambda url, timeout=20: body)
    site, api = oracle._page_config("https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX", 5)
    assert site == "CX_2002"
    assert api == "https://acme.fa.us2.oraclecloud.com"


def test_oracle_page_config_can_infer_fa_host(monkeypatch):
    body = '{"siteNumber":"CX_3003","image":"https://acme.fa.us2.oraclecloud.com:443/hcmRestApi/CandidateExperience/image"}'
    monkeypatch.setattr(oracle, "_get", lambda url, timeout=20: body)
    site, api = oracle._page_config("https://careers.example.com/hcmUI/CandidateExperience/en/sites/CX", 5)
    assert site == "CX_3003"
    assert api == "https://acme.fa.us2.oraclecloud.com:443"
