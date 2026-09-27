from app.batch_prepare import _should_use_master_resume


def test_usable_short_jd_with_targets_is_tailored_not_master():
    raw={"tailoring_mode":"BASE_RESUME_CONSERVATIVE","description_usable":True}
    assert _should_use_master_resume(raw,{"target_count":7}) is False


def test_master_fallback_requires_zero_safe_targets():
    raw={"tailoring_mode":"BASE_RESUME_CONSERVATIVE","description_usable":True}
    assert _should_use_master_resume(raw,{"target_count":0}) is True
