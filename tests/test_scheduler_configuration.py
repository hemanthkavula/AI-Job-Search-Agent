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


def test_cloudflare_utc_schedule_covers_friday_2100_et():
    wrangler = (ROOT / "wrangler.toml").read_text(encoding="utf-8")
    assert 'crons = ["7,22,42 * * * MON-SAT"]' in wrangler

    worker = (ROOT / "cloudflare-scheduler.js").read_text(encoding="utf-8")
    assert "const dueSlots = [[7,30],[10,0],[12,30],[15,30],[18,30],[21,0]];" in worker
    assert "localMinutes < slotMinutes + 55" in worker
    assert 'new Set(["Mon","Tue","Wed","Thu","Fri"])' in worker


def test_github_native_scheduler_fallback_covers_edt_and_est():
    workflow = (ROOT / ".github" / "workflows" / "daily-discovery.yml").read_text(encoding="utf-8")
    assert 'cron: "37 11,12,16,17,19,20,22,23 * * 1-5"' in workflow
    assert 'cron: "7 14,15 * * 1-5"' in workflow
    assert 'cron: "7 1,2 * * 2-6"' in workflow
    assert "state.get(\"last_completed_slot\") != slot" in workflow
