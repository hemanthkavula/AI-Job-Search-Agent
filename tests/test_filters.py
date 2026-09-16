from app.filters import passes_hard_filters
PROFILE={"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"],"max_required_years":7},"work_authorization":{"requires_sponsorship_future":True}}

def test_data_engineer_passes():
    ok,_=passes_hard_filters({"title":"Senior Data Engineer","description":"Python AWS","location":"United States"},PROFILE); assert ok

def test_c2c_rejected():
    ok,r=passes_hard_filters({"title":"AWS Data Engineer","description":"C2C only"},PROFILE); assert not ok

def test_no_sponsorship_rejected():
    ok,r=passes_hard_filters({"title":"Senior Data Engineer","description":"Candidates must be eligible to work in the US without visa sponsorship."},PROFILE)
    assert not ok and any("sponsorship" in x for x in r)

def test_excess_years_rejected():
    ok,r=passes_hard_filters({"title":"Senior Data Engineer","description":"10+ years of professional experience required."},PROFILE)
    assert not ok and any("10+" in x for x in r)

def test_non_us_rejected():
    ok,r=passes_hard_filters({"title":"Data Engineer","description":"Python","location":"South America"},PROFILE); assert not ok
