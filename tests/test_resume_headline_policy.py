from app.reference_resume_formatter import resume_branding_headline


def test_headline_does_not_inflate_seniority():
    assert resume_branding_headline("Staff Analytics Engineer") == "Senior Data Engineer | Analytics Engineering"
    assert resume_branding_headline("Principal Analytics Engineer") == "Senior Data Engineer | Analytics Engineering"
    assert resume_branding_headline("Lead Data Platform Engineer") == "Senior Data Engineer | Data Platform Engineering"


def test_headline_keeps_data_engineer_base_for_same_family_roles():
    assert resume_branding_headline("Senior Data Engineer") == "Senior Data Engineer"
    assert resume_branding_headline("Staff Data Engineer") == "Senior Data Engineer"
    assert resume_branding_headline("Data Engineer") == "Senior Data Engineer"


def test_headline_adds_only_one_truthful_specialty():
    assert resume_branding_headline("Analytics Engineer") == "Senior Data Engineer | Analytics Engineering"
    assert resume_branding_headline("Data Platform Engineer") == "Senior Data Engineer | Data Platform Engineering"
    assert resume_branding_headline("Streaming Data Engineer") == "Senior Data Engineer | Streaming Data Engineering"


def test_headline_adds_ai_ml_data_platform_specialty_without_changing_held_title():
    assert resume_branding_headline("AI/ML Software Engineer") == "Senior Data Engineer | AI/ML & Generative AI Data Platforms"
    assert resume_branding_headline("Generative AI Data Engineer") == "Senior Data Engineer | AI/ML & Generative AI Data Platforms"
