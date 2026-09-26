from app.company_registry import upsert, learn_from_jobs


def test_existing_company_metadata_is_updated_without_new_registry_key():
    registry={}
    upsert(registry,"Example, Inc.",discovered_by="career_site")
    before_keys=set(registry)
    learn_from_jobs([{
      "company":"Example Inc","source":"manatal","ats_provider":"manatal",
      "ats_identifier":"example","original_url":"https://example.manatal.com/jobs"
    }],registry)
    assert set(registry)==before_keys
    row=registry[next(iter(registry))]
    assert row["ats_provider"]=="manatal"
    assert row["ats_identifier"]=="example"
    assert row["careers_url"]=="https://example.manatal.com/jobs"
    assert row["discovered_by"]=="manatal"
