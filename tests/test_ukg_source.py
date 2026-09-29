from app.sources import ukg


def test_ukg_embedded_opportunities_admit_broad_de_family(monkeypatch):
    body='''{"Id":"11111111-1111-1111-1111-111111111111","Featured":false,"Title":"Senior Data Platform Lead","BriefDescription":"Build lakehouse and Spark pipelines","Locations":[]}'''
    monkeypatch.setattr(ukg,"_get",lambda url,timeout=25:body)
    rows=ukg.fetch_jobs("Acme","https://recruiting.example.com/jobs")
    assert len(rows) == 1
    assert rows[0]["title"] == "Senior Data Platform Lead"
    assert rows[0]["ats_provider"] == "ukg"
