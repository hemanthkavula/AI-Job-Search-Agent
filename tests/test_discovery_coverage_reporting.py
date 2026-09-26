import json

from app.discovery import discover


def test_discovery_reports_zero_coverage_for_empty_source_universe(tmp_path):
    registry = tmp_path / "sources.json"
    registry.write_text("{}", encoding="utf-8")
    health = tmp_path / "health.json"
    config = {"career_site": [], "discovery_portal": [], "dice": {"enabled": False}, "ziprecruiter": {"enabled": False}, "monster": {"enabled": False}}

    rows, errors, coverage = discover(
        config,
        registry_path=str(registry),
        health_path=str(health),
        return_coverage=True,
    )

    assert rows == []
    assert errors == []
    assert coverage["unique_employers_or_tenants_attempted"] == 0
    assert coverage["career_site_units_attempted"] == 0
    assert coverage["ats_tenant_units_attempted"] == 0
    assert coverage["ats_provider_families_attempted"] == 0
    assert coverage["job_board_or_discovery_units_attempted"] == 0
    assert coverage["successful_units"] == 0
    assert coverage["failed_units"] == 0


def test_blocked_sources_are_explicitly_disabled_in_production_config():
    cfg = json.load(open("data/job_sources.json", encoding="utf-8"))
    assert cfg["monster"]["enabled"] is False
    assert cfg["bullhorn"] == []
    assert cfg["homerun"] == []
    assert cfg["ziprecruiter"]["enabled"] is True
