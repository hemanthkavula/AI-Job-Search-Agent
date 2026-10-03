from pathlib import Path

from app import scheduled_runner


ROOT = Path(__file__).resolve().parents[1]


def test_requested_production_slots_are_locked():
    assert scheduled_runner.RUN_SLOTS == (
        (7, 30),
        (10, 0),
        (12, 30),
        (15, 30),
        (18, 30),
        (21, 0),
    )
    assert scheduled_runner.SLOT_RECOVERY_MINUTES == 55
    assert scheduled_runner.RUN_WEEKDAYS == {0, 1, 2, 3, 4}


def test_cloudflare_primary_scheduler_covers_production_and_enrichment():
    wrangler = (ROOT / "wrangler.toml").read_text(encoding="utf-8")
    assert '"7,22,42 * * * MON-SAT"' in wrangler
    assert '"30 9,10 * * MON-FRI"' in wrangler

    worker = (ROOT / "cloudflare-scheduler.js").read_text(encoding="utf-8")
    assert 'const PRODUCTION_WORKFLOW = "daily-discovery.yml";' in worker
    assert 'const ENRICHMENT_WORKFLOW = "employer-universe-enrichment.yml";' in worker
    assert 'if (hour === 5 && minute === 30)' in worker
    assert 'domain_budget: "750"' in worker
    assert 'career_budget: "750"' in worker
    assert 'ats_tenant_budget: "250"' in worker
    assert 'deep_domain_search: "true"' in worker
    assert 'scheduled_dispatch: "true"' in worker
    assert "const dueSlots = [[7,30],[10,0],[12,30],[15,30],[18,30],[21,0]];" in worker
    assert "localMinutes < slotMinutes + 55" in worker
    assert 'new Set(["Mon","Tue","Wed","Thu","Fri"])' in worker


def test_github_native_production_scheduler_fallback_covers_edt_and_est():
    workflow = (ROOT / ".github" / "workflows" / "daily-discovery.yml").read_text(encoding="utf-8")
    assert 'cron: "37 11,12,16,17,19,20,22,23 * * 1-5"' in workflow
    assert 'cron: "7 14,15 * * 1-5"' in workflow
    assert 'cron: "7 1,2 * * 2-6"' in workflow
    assert "state.get(\"last_completed_slot\") != slot" in workflow


def test_github_native_enrichment_fallback_is_delayed_idempotent_and_separate():
    workflow = (ROOT / ".github" / "workflows" / "employer-universe-enrichment.yml").read_text(encoding="utf-8")
    # Cloudflare is primary at 05:30 ET; GitHub waits until 05:45 ET so it acts
    # as a fallback rather than racing the primary dispatch.
    assert 'cron: "45 9 * * 1-5"' in workflow
    assert 'cron: "45 10 * * 1-5"' in workflow
    assert "scheduled_dispatch:" in workflow
    assert 'scheduled_dispatch = "${{ inputs.scheduled_dispatch }}" == "true"' in workflow
    assert 'Path("state/employer_universe_last_success.json")' in workflow
    assert "already_succeeded_today" in workflow
    assert "and not already_succeeded_today" in workflow
    assert "python -m app.company_enrichment_runner" in workflow
    assert "app.scheduled_runner" not in workflow

    # The persisted state must be restored before the due/duplicate decision so
    # a queued GitHub fallback can observe the primary run's success marker.
    restore_index = workflow.index("- name: Restore employer/source discovery state")
    guard_index = workflow.index("- name: Decide whether enrichment is due")
    assert restore_index < guard_index
