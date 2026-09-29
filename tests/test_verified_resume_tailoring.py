from app import batch_prepare


def test_verified_resume_pipeline_has_no_master_resume_fallback():
    assert not hasattr(batch_prepare,"_should_use_master_resume")
    assert not hasattr(batch_prepare,"_base_resume_payload")
    assert not hasattr(batch_prepare,"_render_base_resume")
