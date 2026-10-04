from app.batch_prepare import _should_use_master_resume


def test_zero_targets_use_master_resume():
    raw={"tailoring_mode":"FULL_JD","description_usable":True}
    assert _should_use_master_resume(raw,{"target_count":0}) is True


def test_every_nonzero_target_set_is_tailored():
    raw={"tailoring_mode":"FULL_JD","description_usable":True}
    for target_count in (1,2,3,7,15):
        assert _should_use_master_resume(raw,{"target_count":target_count}) is False
