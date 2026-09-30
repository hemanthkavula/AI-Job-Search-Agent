from app.discovery_health import build_source_execution_matrix, evaluate_discovery_health


def test_matrix_reports_unaccounted_configured_units():
    units={
        "lever:a":{"source":"lever","company":"a","status":"OK","jobs_returned":5},
        "lever:b":{"source":"lever","company":"b","status":"ERROR","jobs_returned":0},
        "ashby:c":{"source":"ashby","company":"c","status":"SKIPPED_UNHEALTHY","jobs_returned":0},
    }
    coverage={"configured_units_by_provider":{"lever":3,"ashby":1}}
    matrix=build_source_execution_matrix(units,coverage)
    assert matrix["lever"]["configured_units"]==3
    assert matrix["lever"]["attempted_units"]==2
    assert matrix["lever"]["unaccounted_configured_units"]==1
    assert matrix["ashby"]["skipped_units"]==1


def test_discovery_health_can_be_degraded_when_workflow_succeeds():
    matrix={"lever":{"configured_units":10,"attempted_units":8,"successful_units":8,"failed_units":0,"skipped_units":0,"zero_result_units":0,"raw_jobs":100,"unaccounted_configured_units":2}}
    health=evaluate_discovery_health(coverage={"configured_units_by_provider":{"lever":10}},source_matrix=matrix,discovered=100,missing_dates=50,healthy_baseline_discovered=1000)
    assert health["status"]=="DEGRADED"
    assert health["unaccounted_configured_units"]==2
    assert any("posting-date" in x for x in health["warnings"])
    assert any("baseline" in x for x in health["warnings"])


def test_healthy_when_execution_is_accounted_and_rates_are_normal():
    matrix={"lever":{"configured_units":2,"attempted_units":2,"successful_units":2,"failed_units":0,"skipped_units":0,"zero_result_units":0,"raw_jobs":100,"unaccounted_configured_units":0}}
    health=evaluate_discovery_health(coverage={"configured_units_by_provider":{"lever":2}},source_matrix=matrix,discovered=100,missing_dates=10,healthy_baseline_discovered=110)
    assert health["status"]=="HEALTHY"
    assert health["warnings"]==[]
