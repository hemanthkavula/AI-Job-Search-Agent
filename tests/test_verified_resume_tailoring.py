from app.batch_prepare import _should_use_master_resume


def test_usable_jd_with_three_or_more_targets_is_tailored_not_master():
    raw={"tailoring_mode":"FULL_JD","description_usable":True}
    assert _should_use_master_resume(raw,{"target_count":3}) is False
    assert _should_use_master_resume(raw,{"target_count":7}) is False


def test_master_resume_used_for_zero_one_or_two_targets():
    raw={"tailoring_mode":"BASE_RESUME_CONSERVATIVE","description_usable":True}
    for target_count in (0,1,2):
        assert _should_use_master_resume(raw,{"target_count":target_count}) is True
