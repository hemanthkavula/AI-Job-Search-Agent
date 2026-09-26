from app.daily_runner import _dedup_eligible, SOURCE_PRIORITY


def test_long_tail_direct_ats_beats_career_site_and_aggregator_duplicate():
    common={"company":"Example Inc","title":"Senior Data Engineer","location":"United States","requisition_id":"123"}
    dice={"job":dict(common,source="dice",external_id="dice:123",url="https://dice.example/123")}
    career={"job":dict(common,source="career_site",external_id="career:123",url="https://example.com/jobs/123")}
    manatal={"job":dict(common,source="manatal",external_id="manatal:123",url="https://example.manatal.com/jobs/123")}
    kept,duplicates=_dedup_eligible([dice,career,manatal])
    assert SOURCE_PRIORITY["manatal"]==0
    assert SOURCE_PRIORITY["ceipal"]==0
    assert SOURCE_PRIORITY["career_site"]==1
    assert SOURCE_PRIORITY["dice"]==2
    assert len(kept)==1
    assert kept[0]["job"]["source"]=="manatal"
    assert len(duplicates)==2
