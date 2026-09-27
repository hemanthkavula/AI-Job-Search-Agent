import json
from datetime import datetime
import app.scheduled_runner as runner

def test_enabled_discovery_portal_gets_provider_watermark(monkeypatch,tmp_path):
    source=tmp_path/"sources.json"
    source.write_text(json.dumps({"discovery_portal":[{"provider":"wellfound","enabled":True}]}))
    monkeypatch.setattr(runner,"ROOT",tmp_path)
    monkeypatch.setattr(runner,"STATE_PATH",tmp_path/"scheduler_state.json")
    monkeypatch.setattr(runner,"RUN_WEEKDAYS",set(range(7)))
    monkeypatch.setattr(runner,"run_cycle",lambda **kwargs:{
        "cycle_id":"test","source_status":{"wellfound":"OK"},"source_errors":{}
    })
    result=runner.run_scheduled("sources.json",str(tmp_path/"ledger.json"),generate_resumes=False,force=True)
    assert "wellfound" in result["source_watermarks"]
