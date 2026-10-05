from app.batch_prepare import _should_use_master_resume


def test_zero_to_two_targets_use_master_resume():
    raw={"tailoring_mode":"FULL_JD","description_usable":True,"description_complete":True}
    for target_count in (0,1,2):
        assert _should_use_master_resume(raw,{"target_count":target_count}) is True


def test_three_or_more_complete_targets_are_tailored():
    raw={"tailoring_mode":"FULL_JD","description_usable":True,"description_complete":True}
    for target_count in (3,7,15):
        assert _should_use_master_resume(raw,{"target_count":target_count}) is False


def test_partial_or_conservative_jd_uses_master_even_with_more_targets():
    conservative={"tailoring_mode":"BASE_RESUME_CONSERVATIVE","description_usable":True}
    incomplete={"tailoring_mode":"FULL_JD","description_usable":True,"description_complete":False}
    assert _should_use_master_resume(conservative,{"target_count":5}) is True
    assert _should_use_master_resume(incomplete,{"target_count":5}) is True
