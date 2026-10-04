from app.filters import location_is_us


def test_workday_india_country_code_is_not_indiana():
    assert location_is_us("IN, Bangalore Kar", "workday", "") is False
    assert location_is_us("IN, Bengaluru Karnataka", "workday", "") is False


def test_real_indiana_location_still_qualifies():
    assert location_is_us("Indianapolis, IN", "workday", "") is True
    assert location_is_us("Indianapolis, Indiana", "workday", "") is True


def test_foreign_location_wins_before_state_abbreviation():
    assert location_is_us("IN, Bangalore Kar | Hyderabad, India", "workday", "") is False


def test_foreign_markers_require_token_boundaries():
    assert location_is_us("Indianapolis, IN", "workday", "") is True
    assert location_is_us("India", "workday", "") is False
    assert location_is_us("Bangalore, India", "workday", "") is False


def test_generic_remote_requires_us_scope_for_workday():
    assert location_is_us("Remote", "workday", "Remote within the United States") is True
    assert location_is_us("Remote", "workday", "Remote role based in India") is False
