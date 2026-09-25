from app.sources import career_site

def test_jobpostings_reads_graph_and_list():
    body='''<script type="application/ld+json">{"@graph":[{"@type":"Organization","name":"Acme"},{"@type":"JobPosting","title":"Data Engineer","url":"https://acme.test/jobs/1"}]}</script><script type="application/ld+json">[{"@type":"JobPosting","title":"Senior Data Engineer","url":"https://acme.test/jobs/2"}]</script>'''
    rows=career_site._jobpostings(body)
    assert [r["title"] for r in rows] == ["Data Engineer","Senior Data Engineer"]

def test_canonical_url_removes_tracking_and_fragment():
    assert career_site._canonical_url("https://acme.test/jobs/1?utm_source=board#apply") == "https://acme.test/jobs/1"

def test_expired_and_unknown_freshness():
    assert career_site._freshness({"validThrough":"2000-01-01T00:00:00Z"}) == "expired"
    assert career_site._freshness({}) == "unknown"

def test_source_quality_is_evidence_not_eligibility():
    evidence=career_site._source_quality({"@type":"JobPosting","url":"https://acme.test/jobs/1","identifier":{"value":"1"}})
    assert evidence["has_structured_jobposting"] is True
    assert evidence["has_direct_job_url"] is True
    assert evidence["has_stable_identifier"] is True
    assert "eligible" not in evidence
