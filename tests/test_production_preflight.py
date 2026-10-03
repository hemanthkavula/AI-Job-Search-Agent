import json
from pathlib import Path

from app import config
from app.production_preflight import normalize_source_health, validate_requirements


def test_runtime_profile_includes_broad_data_engineering_family(monkeypatch, tmp_path):
    profile = {
        "preferences": {"target_roles": ["Data Engineer", "Senior Data Engineer"]},
        "master_resume_reference": {
            "layout_version": "master-2026-10-03",
            "bullet_counts": {
                "Fidelity Investments": 10,
                "Cigna Healthcare": 8,
                "Target Corporation": 8,
            },
        },
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_PATH", path)
    loaded = config.load_profile()
    roles = loaded["preferences"]["target_roles"]
    assert roles[:2] == ["Data Engineer", "Senior Data Engineer"]
    assert "Analytics Engineer" in roles
    assert "Data Platform Engineer" in roles
    assert "Data Infrastructure Engineer" in roles
    assert "Data Pipeline Engineer" in roles


def test_source_health_keyed_runtime_format_is_normalized_for_discovery(tmp_path):
    health = tmp_path / "source_health.json"
    health.write_text(
        json.dumps(
            {
                "workday:Broken Co": {
                    "source": "workday",
                    "company": "Broken Co",
                    "status": "ERROR",
                    "error": "HTTP Error 404: Not Found",
                    "checked_at": "2026-10-03T12:00:00+00:00",
                },
                "greenhouse:Healthy Co": {
                    "source": "greenhouse",
                    "company": "Healthy Co",
                    "status": "OK",
                    "checked_at": "2026-10-03T12:01:00+00:00",
                },
            }
        ),
        encoding="utf-8",
    )
    result = normalize_source_health(health)
    assert result["rows"] == 2
    assert result["quarantined"] == 1
    payload = json.loads(health.read_text(encoding="utf-8"))
    rows = {(row["provider"], row["company"]): row for row in payload["sources"]}
    assert rows[("workday", "Broken Co")]["effective_status"] == "broken"
    assert rows[("greenhouse", "Healthy Co")]["effective_status"] == "ok"


def test_skipped_unhealthy_does_not_erase_prior_failure_classification(tmp_path):
    health = tmp_path / "source_health.json"
    health.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "provider": "career_site",
                        "source": "career_site",
                        "company": "Blocked Co",
                        "status": "ERROR",
                        "effective_status": "blocked_or_http_error",
                        "checked_at": "2026-10-03T10:00:00+00:00",
                    }
                ],
                "career_site:Blocked Co": {
                    "source": "career_site",
                    "company": "Blocked Co",
                    "status": "SKIPPED_UNHEALTHY",
                    "checked_at": "2026-10-03T12:00:00+00:00",
                },
            }
        ),
        encoding="utf-8",
    )
    normalize_source_health(health)
    payload = json.loads(health.read_text(encoding="utf-8"))
    assert payload["sources"][0]["effective_status"] == "blocked_or_http_error"


def test_requirements_contract_passes_current_repository():
    result = validate_requirements()
    assert result["passed"], result["failures"]
