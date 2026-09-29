import pytest
from app.resume_generator import generate_resume


def test_legacy_profile_derived_resume_generation_is_disabled():
    with pytest.raises(RuntimeError,match="Legacy generate_resume is disabled"):
        generate_resume(None,None,None)
