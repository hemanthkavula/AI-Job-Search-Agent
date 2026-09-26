from app import career_page_resolver as resolver

def test_resolver_detects_embedded_ats_script_and_keeps_employer_url(monkeypatch):
    root='<a href="/careers">Careers</a>'
    careers='<script src="https://cdn.phenompeople.com/assets/app.js"></script><div>Search jobs</div>'
    def fake_get(url,timeout=15):
        if url.rstrip("/")=="https://example.com":
            return "https://example.com/",root
        return "https://example.com/careers",careers
    monkeypatch.setattr(resolver,"_get",fake_get)
    result=resolver.resolve("example.com")
    assert result["ats_provider"]=="phenom"
    assert result["careers_url"]=="https://example.com/careers"
