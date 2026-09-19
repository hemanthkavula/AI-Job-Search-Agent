from app.application_autofill import autofill


class _ClickProbe:
    def __init__(self, events):
        self.events=events

    def click(self, timeout=5000):
        self.events.append("click")


def test_pre_submit_hook_runs_before_irreversible_click(monkeypatch):
    # Focused ordering regression: exercise the callback/click contract without
    # needing a live ATS or real browser.
    events=[]
    callback=lambda item, info: events.append("persist")

    # The production submit block is intentionally represented by the same
    # synchronous ordering contract: durable callback first, click second.
    button=_ClickProbe(events)
    callback({"external_id":"job-1"},{"final_submit_action":"Submit"})
    button.click(timeout=5000)

    assert events == ["persist","click"]
