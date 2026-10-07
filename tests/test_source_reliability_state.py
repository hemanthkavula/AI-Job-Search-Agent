from datetime import datetime, timezone

from app import source_reliability


NOW=datetime(2026,10,7,14,0,tzinfo=timezone.utc)


def _err(message="request timeout"):
    return {"source":"workday","company":"Example","status":"ERROR","error":message}


def test_transient_failures_retry_twice_then_backoff(tmp_path):
    path=tmp_path/"retry.json"
    key="workday:Example"
    source_reliability.update_from_cycle({key:_err()},now=NOW,path=path)
    assert source_reliability.retry_decision(key,now=NOW,path=path)["attempt"] is True

    source_reliability.update_from_cycle({key:_err()},now=NOW,path=path)
    assert source_reliability.retry_decision(key,now=NOW,path=path)["attempt"] is True

    state=source_reliability.update_from_cycle({key:_err()},now=NOW,path=path)
    assert state["units"][key]["consecutive_failures"]==3
    decision=source_reliability.retry_decision(key,now=NOW,path=path)
    assert decision["attempt"] is False
    assert decision["reason"]=="TRANSIENT_BACKOFF"


def test_success_resets_failure_state(tmp_path):
    path=tmp_path/"retry.json"
    key="icims:Example"
    source_reliability.update_from_cycle({key:{"source":"icims","company":"Example","status":"ERROR","error":"HTTP 503"}},now=NOW,path=path)
    state=source_reliability.update_from_cycle({key:{"source":"icims","company":"Example","status":"OK"}},now=NOW,path=path)
    row=state["units"][key]
    assert row["consecutive_failures"]==0
    assert row["repair_required"] is not True
    assert source_reliability.retry_decision(key,now=NOW,path=path)["attempt"] is True


def test_hard_failure_goes_directly_to_repair(tmp_path):
    path=tmp_path/"retry.json"
    key="oracle:Dead Co"
    state=source_reliability.update_from_cycle({
        key:{"source":"oracle","company":"Dead Co","status":"ERROR","error":"HTTP 404: Not Found"}
    },now=NOW,path=path)
    row=state["units"][key]
    assert row["failure_class"]=="hard"
    assert row["repair_required"] is True
    decision=source_reliability.retry_decision(key,now=NOW,path=path)
    assert decision["attempt"] is False
    assert decision["reason"]=="HARD_FAILURE_AWAITING_REPAIR"
