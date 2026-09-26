from app.daily_runner import _dedup_eligible


def _item(source,url,external_id,req=None,location="United States"):
    job={"source":source,"company":"Example Inc","company_key":"Example Inc","title":"Senior Data Engineer","location":location,"url":url,"external_id":external_id}
    if req: job["requisition_id"]=req
    return {"job":job,"eligibility":{},"action":"ELIGIBLE_FOR_RESUME"}


def test_direct_ats_wins_over_aggregator_for_same_requisition():
    direct=_item("lever","https://jobs.lever.co/example/abc","lever:abc","REQ-42")
    broad=_item("dice","https://www.dice.com/job-detail/123","dice:123","REQ-42")
    kept,dupes=_dedup_eligible([broad,direct])
    assert [x["job"]["source"] for x in kept]==["lever"]
    assert dupes[0]["job"]["source"]=="dice"


def test_canonical_url_alias_collapses_tracking_variants():
    direct=_item("greenhouse","https://boards.greenhouse.io/example/jobs/42?gh_src=abc","gh:42")
    broad=_item("dice","https://boards.greenhouse.io/example/jobs/42?utm_source=dice","dice:42")
    kept,dupes=_dedup_eligible([broad,direct])
    assert len(kept)==1
    assert kept[0]["job"]["source"]=="greenhouse"
    assert len(dupes)==1
