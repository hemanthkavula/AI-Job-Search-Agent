from app.browser.common import is_sensitive

def test_sensitive_questions():
    assert is_sensitive("Will you now or in the future require sponsorship?")
    assert is_sensitive("Desired salary")
    assert not is_sensitive("LinkedIn URL")
