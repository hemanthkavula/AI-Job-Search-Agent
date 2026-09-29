def test_legacy_master_resume_helpers_are_removed():
    import app.batch_prepare as batch_prepare
    assert not hasattr(batch_prepare,"_base_resume_payload")
    assert not hasattr(batch_prepare,"_render_base_resume")
    assert not hasattr(batch_prepare,"_should_use_master_resume")
