from app import job_identity


def test_canonical_fallback_is_self_contained(monkeypatch):
    # Force the defensive fallback branch. It should never depend on a local
    # variable created only inside identity_keys().
    monkeypatch.setattr(job_identity,"identity_keys",lambda job:[])
    key=job_identity.canonical_job_key({
      "company":"Example, Inc.","title":"Senior Data Engineer (Remote)",
      "location":"United States","url":"https://example.com/jobs/123?utm_source=test"
    })
    assert key.startswith("job:")
    assert len(key) > 4


def test_url_normalization_removes_tracking_query_and_fragment():
    a=job_identity.normalize_url("HTTPS://Example.COM/jobs/123/?utm_source=x#apply")
    b=job_identity.normalize_url("https://example.com/jobs/123")
    assert a==b
