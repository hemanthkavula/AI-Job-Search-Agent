from app.company_registry import company_key


def test_company_key_removes_legal_suffixes_and_collapses_whitespace():
    assert company_key("  Example   Holdings, Inc.  ")=="example"
    assert company_key("Example Corporation")=="example"
