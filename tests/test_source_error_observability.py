from app import daily_runner


def test_discovery_report_groups_provider_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(daily_runner, "load_profile", lambda: {})
    monkeypatch.setattr(daily_runner, "load_sources", lambda path: {
        "workday": [
            {"company": "Example", "tenant": "example"},
            {"company": "Other", "tenant": "other"},
        ],
        "ziprecruiter": {"enabled": True},
    })
    monkeypatch.setattr(
        daily_runner,
        "discover",
        lambda *args, **kwargs: (
            [],
            [
                {"source": "workday", "company": "Example", "error": "request timeout"},
                {"source": "workday", "company": "Other", "error": "HTTP 503"},
                {"source": "ziprecruiter", "error": "HTTP 403"},
            ],
        ),
    )
    monkeypatch.setattr(daily_runner, "load_ledger", lambda path: {"jobs": {}, "aliases": {}})
    monkeypatch.setattr(daily_runner, "save_ledger", lambda ledger, path: None)

    report = daily_runner.run(
        "unused.json",
        hours=1,
        ledger_path=str(tmp_path / "ledger.json"),
    )

    assert report["source_status"]["workday"] == "ERROR"
    assert report["source_status"]["ziprecruiter"] == "ERROR"
    assert len(report["source_errors"]["workday"]) == 2
    assert report["source_errors"]["workday"][0]["error"] == "request timeout"
    assert report["source_errors"]["ziprecruiter"][0]["error"] == "HTTP 403"

    assert report["source_unit_status"]["workday:Example"] == "ERROR"
    assert report["source_unit_status"]["workday:Other"] == "ERROR"
