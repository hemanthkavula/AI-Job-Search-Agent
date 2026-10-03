import asyncio
import json
from pathlib import Path

import app.application_stage as stage


def test_empty_queue_enables_stage_without_browser_dependency(tmp_path, monkeypatch):
    cycles = tmp_path / "generated" / "cycles"
    cycles.mkdir(parents=True)
    queue = cycles / "cycle_application_queue.json"
    queue.write_text("[]", encoding="utf-8")
    summary = cycles / "cycle_summary.json"
    summary.write_text(json.dumps({"application_queue": str(queue), "application_stage_enabled": False}), encoding="utf-8")

    monkeypatch.setattr(stage, "ROOT", tmp_path)
    monkeypatch.setattr(stage, "CYCLES_DIR", cycles)
    monkeypatch.setattr(stage, "RESULTS_PATH", tmp_path / "generated" / "application_stage_results.json")

    result = asyncio.run(stage.run(queue=str(queue), ledger_path=tmp_path / "generated" / "job_ledger.json", allow_submit=True))
    assert result["processed"] == 0
    updated = json.loads(summary.read_text(encoding="utf-8"))
    assert updated["application_stage_enabled"] is True
    assert updated["applications_processed"] == 0
    assert updated["applications_submitted"] == 0
