from app.filters import passes_hard_filters

def test_target_role_is_accepted():
    profile={"preferences":{"target_roles":["Data Engineer","Senior Data Engineer"]}}
    ok,_=passes_hard_filters({"title":"Senior Data Engineer","description":"Python SQL AWS"},profile)
    assert ok
