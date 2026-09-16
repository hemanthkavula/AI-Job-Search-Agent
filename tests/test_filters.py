from app.filters import passes_hard_filters

PROFILE={"preferences":{"target_roles":["Data Engineer","Senior Data Engineer","AWS Data Engineer","Azure Data Engineer","Lead Data Engineer"]}}

def test_data_engineer_passes():
    ok,_=passes_hard_filters({"title":"Senior Data Engineer","description":"Python AWS"},PROFILE)
    assert ok

def test_c2c_rejected():
    ok,reasons=passes_hard_filters({"title":"AWS Data Engineer","description":"C2C only"},PROFILE)
    assert not ok
    assert reasons
