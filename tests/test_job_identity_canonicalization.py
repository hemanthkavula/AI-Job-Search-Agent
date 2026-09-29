from app.job_identity import identity_keys, semantic_job_key

def test_identity_retains_aggregator_url_after_official_ats_resolution():
    discovery={
        "company":"Example Inc","title":"Senior Data Engineer","location":"United States",
        "url":"https://www.dice.com/job-detail/abc"
    }
    finalized={
        "company":"Example Inc","title":"Senior Data Engineer","location":"New York, NY, United States",
        "discovery_location":"United States",
        "url":"https://jobs.example.com/job/123","original_url":"https://jobs.example.com/job/123",
        "aggregator_url":"https://www.dice.com/job-detail/abc"
    }
    assert set(identity_keys(discovery)) & set(identity_keys(finalized))

def test_identity_retains_discovery_location_semantic_alias():
    discovery={"company":"Example Inc","title":"Data Engineer","location":"United States"}
    finalized={
        "company":"Example Inc","title":"Data Engineer","location":"Jersey City, NJ, United States",
        "discovery_location":"United States"
    }
    assert semantic_job_key(discovery) in identity_keys(finalized)
