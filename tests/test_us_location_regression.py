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
    assert location_is_us("Remote", "workday", "This role is based in the United States") is True
    assert location_is_us("Remote", "workday", "Remote role based in India") is False


def test_explicit_emea_location_cannot_be_overridden_by_us_team_mention():
    description = "Our distributed team has employees in the USA, Canada, UK, and Switzerland."
    assert location_is_us("Remote - EMEA", "greenhouse", description) is False


def test_global_and_worldwide_roles_are_not_us_based():
    assert location_is_us("Remote - Global", "greenhouse", "We have offices in the USA") is False
    assert location_is_us("Worldwide", "lever", "Our company serves United States customers") is False


def test_missing_location_needs_explicit_us_vacancy_scope():
    assert location_is_us("", "greenhouse", "Our engineering team includes people in the USA and Europe") is False
    assert location_is_us("", "greenhouse", "This position is based in the United States") is True


def test_application_question_can_prove_us_scope_when_location_missing():
    question = "Are you currently located in the United States?"
    assert location_is_us("", "greenhouse", "", question) is True


def test_unknown_dice_location_is_not_assumed_us():
    assert location_is_us("", "dice", "Python SQL Spark data engineering") is False
