import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import app.daily_runner as daily_runner
import app.scheduled_runner as scheduled_runner
from app.eligibility import experience_check
from app.filters import location_is_us


def test_remote_us_scope_from_jd_is_accepted_for_direct_ats():
    assert location_is_us(
        "Remote",
        source="greenhouse",
        description="This is a full-time role remote within the United States.",
    )


def test_remote_foreign_scope_is_not_mistaken_for_indiana():
    # The old case-insensitive state regex could read the word "in" as IN.
    assert not location_is_us("Remote in Canada", source="wellfound", description="")


def test_locationless_direct_ats_can_use_explicit_us_scope_from_jd():
    assert location_is_us(
        "",
        source="ashby",
        description="Candidates may work anywhere in the United States.",
    )


def test_experience_window_preserves_exclusive_upper_bound():
    profile={
        "candidate_experience_years":5,
        "preferences":{"min_required_years":3,"max_required_years":7},
    }
    six=experience_check(
        {"title":"Senior Data Engineer","description":"Requires 6 years of relevant experience."},
        profile,
    )
    seven=experience_check(
        {"title":"Senior Data Engineer","description":"Requires 7 years of relevant experience."},
        profile,
    )
    assert six["eligible"] is True
    assert seven["eligible"] is False


def test_provider_status_uses_current_health_for_learned_provider():
    coverage={"configured_units_by_provider":{"wellfound":1}}
    health=[{"source":"wellfound","company":"Wellfound","status":"OK"}]
    status=daily_runner._provider_statuses({},coverage,[],health)
    assert status == {"wellfound":"OK"}


def test_provider_status_distinguishes_partial_failure_from_quarantine():
    coverage={"configured_units_by_provider":{"greenhouse":2,"career_site":1}}
    health=[
        {"source":"greenhouse","company":"A","status":"OK"},
        {"source":"greenhouse","company":"B","status":"ERROR"},
        {"source":"career_site","company":"C","status":"SKIPPED_UNHEALTHY"},
    ]
    status=daily_runner._provider_statuses({},coverage,[],health)
    assert status["greenhouse"] == "PARTIAL"
    assert status["career_site"] == "DEGRADED"


def test_current_health_rows_ignore_previous_cycle_success(tmp_path):
    start=datetime.now(timezone.utc)
    health_path=tmp_path/"source_health.json"
    health_path.write_text(json.dumps({
        "old":{"source":"workday","company":"OldCo","status":"OK","checked_at":(start-timedelta(hours=3)).isoformat()},
        "new":{"source":"workday","company":"NewCo","status":"ERROR","checked_at":(start+timedelta(seconds=1)).isoformat()},
    }))
    rows=daily_runner._current_health_rows(start,health_path)
    assert [row["company"] for row in rows] == ["NewCo"]


def test_source_specific_cutoff_is_preserved_for_finalizer(monkeypatch,tmp_path):
    source=tmp_path/"sources.json"
    source.write_text(json.dumps({"discovery_portal":[{"provider":"wellfound","enabled":True}]}))
    cutoff="2026-10-02T21:00:00-04:00"
    job={
        "external_id":"wellfound:1","source":"wellfound","company_key":"Example Co",
        "title":"Data Engineer","location":"Remote - US","employment_type":"Full-Time",
        "url":"https://wellfound.com/jobs/1","posted_at":"2026-10-03T12:00:00Z",
        "description":"Build data pipelines with Python SQL Spark and Snowflake.",
    }
    monkeypatch.setattr(daily_runner,"load_profile",lambda:{})
    monkeypatch.setattr(daily_runner,"load_ledger",lambda path:{})
    monkeypatch.setattr(daily_runner,"save_ledger",lambda *args,**kwargs:None)
    monkeypatch.setattr(daily_runner,"load_company_registry",lambda:{})
    monkeypatch.setattr(daily_runner,"learn_companies_from_jobs",lambda *args,**kwargs:None)
    monkeypatch.setattr(daily_runner,"save_company_registry",lambda *args,**kwargs:None)
    monkeypatch.setattr(daily_runner,"discover",lambda *args,**kwargs:([job],[],{"configured_units_by_provider":{"wellfound":1}}))
    monkeypatch.setattr(daily_runner,"seen_or_submitted",lambda *args,**kwargs:(False,None,None))
    monkeypatch.setattr(daily_runner,"record_seen",lambda *args,**kwargs:None)
    monkeypatch.setattr(daily_runner,"two_category_filter",lambda *args,**kwargs:{"eligible":True,"sponsorship":{"category":"SPONSORSHIP_NOT_STATED"}})
    monkeypatch.setattr(daily_runner,"passes_hard_filters",lambda *args,**kwargs:(True,[]))
    monkeypatch.setattr(daily_runner,"_current_health_rows",lambda start:[{"source":"wellfound","company":"Wellfound","status":"OK"}])
    captured={}
    def fake_fresh(rows,hours,since=None,now=None):
        captured["since"]=since
        captured["cutoff"]=rows[0].get("freshness_cutoff")
        return rows,[],[]
    monkeypatch.setattr(daily_runner,"fresh_jobs",fake_fresh)
    result=daily_runner.run(str(source),hours=2.5,ledger_path=str(tmp_path/"ledger.json"),source_since={"wellfound":cutoff})
    assert captured == {"since":cutoff,"cutoff":cutoff}
    assert result["results"][0]["job"]["freshness_cutoff"] == cutoff
    assert result["source_status"]["wellfound"] == "OK"


def test_scheduler_understands_diagnostic_status_objects():
    assert scheduled_runner._status_code({"status":"OK"}) == "OK"
    assert scheduled_runner._status_code({"status":"SKIPPED_UNHEALTHY"}) == "SKIPPED_UNHEALTHY"


def test_partial_provider_keeps_slot_open_for_recovery(monkeypatch,tmp_path):
    source=tmp_path/"sources.json"
    source.write_text(json.dumps({"greenhouse":[{"company":"A","board_token":"a"}]}))
    monkeypatch.setattr(scheduled_runner,"ROOT",tmp_path)
    monkeypatch.setattr(scheduled_runner,"STATE_PATH",tmp_path/"scheduler_state.json")
    monkeypatch.setattr(scheduled_runner,"load_registry",lambda:{})
    monkeypatch.setattr(scheduled_runner,"as_discovery_config",lambda registry:{})
    monkeypatch.setattr(scheduled_runner,"run_cycle",lambda **kwargs:{
        "cycle_id":"test-partial","source_status":{"greenhouse":"PARTIAL"},"source_errors":{},"source_unit_status":{}
    })
    result=scheduled_runner.run_scheduled("sources.json",str(tmp_path/"ledger.json"),generate_resumes=False,force=True)
    state=json.loads((tmp_path/"scheduler_state.json").read_text())
    assert result["cycle_status"] == "PARTIAL"
    assert result["failed_providers"] == ["greenhouse"]
    assert "last_completed_slot" not in state


def test_degraded_quarantined_provider_closes_slot_without_advancing_watermark(monkeypatch,tmp_path):
    source=tmp_path/"sources.json"
    source.write_text(json.dumps({"career_site":[{"company":"A","search_url":"https://a.example/jobs","job_url_pattern":".+"}]}))
    monkeypatch.setattr(scheduled_runner,"ROOT",tmp_path)
    monkeypatch.setattr(scheduled_runner,"STATE_PATH",tmp_path/"scheduler_state.json")
    monkeypatch.setattr(scheduled_runner,"load_registry",lambda:{})
    monkeypatch.setattr(scheduled_runner,"as_discovery_config",lambda registry:{})
    monkeypatch.setattr(scheduled_runner,"run_cycle",lambda **kwargs:{
        "cycle_id":"test-degraded","source_status":{"career_site":"DEGRADED"},"source_errors":{},"source_unit_status":{}
    })
    result=scheduled_runner.run_scheduled("sources.json",str(tmp_path/"ledger.json"),generate_resumes=False,force=True)
    state=json.loads((tmp_path/"scheduler_state.json").read_text())
    assert result["cycle_status"] == "DEGRADED"
    assert result["degraded_providers"] == ["career_site"]
    assert state.get("last_completed_slot")
    assert result["source_watermarks"]["career_site"] != state["last_run_at"]


def test_enrichment_has_dst_safe_preproduction_schedule():
    text=Path(".github/workflows/employer-universe-enrichment.yml").read_text(encoding="utf-8")
    assert 'cron: "50 10 * * 1-5"' in text
    assert 'cron: "50 11 * * 1-5"' in text
    assert "now.hour == 6" in text
    assert "scheduled_dispatch" in text
    assert "already_succeeded_today" in text
    assert "--domain-budget \"${{ inputs.domain_budget || '750' }}\"" in text
