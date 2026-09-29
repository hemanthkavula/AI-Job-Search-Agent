from app.sources import successfactors


def test_successfactors_searches_broad_de_family_and_deduplicates(monkeypatch):
    calls=[]
    listing='<a href="/job/us/platform-role/123/">role</a>'
    detail='<title>Senior Data Platform Engineer</title><main>Build Spark ETL pipelines and data infrastructure.</main>'
    def fake_get(url, timeout=20):
        calls.append(url)
        return detail if "/job/us/" in url else listing
    monkeypatch.setattr(successfactors,"_get",fake_get)
    rows=successfactors.fetch_jobs("Acme","https://jobs.example.com/")
    assert len(rows) == 1
    assert rows[0]["title"] == "Senior Data Platform Engineer"
    assert rows[0]["ats_provider"] == "successfactors"
    searches=[u for u in calls if "/search/" in u]
    assert len(searches) >= 7
    assert any("data+platform" in u for u in searches)
    assert any("analytics+engineer" in u for u in searches)
