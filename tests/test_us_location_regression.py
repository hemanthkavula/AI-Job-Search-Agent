from app.filters import location_is_us


def test_workday_india_country_code_is_not_indiana():
    assert location_is_us("IN, Bangalore Kar", "workday", "") is False
    assert location_is_us("IN, Bengaluru Karnataka", "workday", "") is False


def test_real_indiana_location_still_qualifies():
    assert location_is_us("Indianapolis, IN", "workday", "") is True
    assert location_is_us("Indianapolis, Indiana", "workday", "") is True


def test_foreign_location_wins_before_state_abbreviation_without_us_role_evidence():
    assert location_is_us("IN, Bangalore Kar | Hyderabad, India", "workday", "") is False


def test_foreign_markers_require_token_boundaries():
    assert location_is_us("Indianapolis, IN", "workday", "") is True
    assert location_is_us("India", "workday", "") is False
    assert location_is_us("Bangalore, India", "workday", "") is False


def test_generic_remote_requires_us_scope_for_workday():
    assert location_is_us("Remote", "workday", "This role is based in the United States") is True
    assert location_is_us("Remote", "workday", "Remote role based in India") is False


def test_emea_label_is_not_overridden_by_generic_us_company_mention():
    description = "Our distributed team has employees in the USA, Canada, UK, and Switzerland."
    assert location_is_us("Remote - EMEA", "greenhouse", description) is False


def test_emea_label_can_be_resolved_by_explicit_us_vacancy_scope_in_full_jd():
    description = "This position is based in the United States and may be performed remotely from the U.S."
    assert location_is_us("Remote - EMEA", "greenhouse", description) is True


def test_emea_label_can_be_resolved_by_us_application_location_question():
    question = "Are you currently located in the United States?"
    assert location_is_us("Remote - EMEA", "greenhouse", "", question) is True


def test_global_and_worldwide_labels_need_explicit_us_vacancy_evidence():
    assert location_is_us("Remote - Global", "greenhouse", "We have offices in the USA") is False
    assert location_is_us("Worldwide", "lever", "Our company serves United States customers") is False
    assert location_is_us("Remote - Global", "greenhouse", "This role is based in the United States") is True


def test_missing_location_needs_explicit_us_vacancy_scope():
    assert location_is_us("", "greenhouse", "Our engineering team includes people in the USA and Europe") is False
    assert location_is_us("", "greenhouse", "This position is based in the United States") is True


def test_application_question_can_prove_us_scope_when_location_missing():
    question = "Are you currently located in the United States?"
    assert location_is_us("", "greenhouse", "", question) is True


def test_unknown_dice_location_is_not_assumed_us():
    assert location_is_us("", "dice", "Python SQL Spark data engineering") is False
