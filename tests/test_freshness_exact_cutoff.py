from datetime import datetime, timezone

import app.freshness as freshness


def test_exact_since_boundary_is_inclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(freshness,"STATE",tmp_path/"seen.json")
    monkeypatch.setattr(freshness,"STATUS",tmp_path/"status.json")
    now=datetime(2026,9,22,12,0,tzinfo=timezone.utc)
    jobs=[
        {"external_id":"at","updated_at":"2026-09-22T11:00:00+00:00"},
        {"external_id":"before","updated_at":"2026-09-22T10:59:59+00:00"},
    ]
    fresh,stale,_=freshness.fresh_jobs(
        jobs,hours=99,since="2026-09-22T11:00:00+00:00",now=now
    )
    assert [x["external_id"] for x in fresh]==["at"]
    assert [x["external_id"] for x in stale]==["before"]


def test_exact_since_does_not_drift_with_runtime_clock(tmp_path, monkeypatch):
    monkeypatch.setattr(freshness,"STATE",tmp_path/"seen.json")
    monkeypatch.setattr(freshness,"STATUS",tmp_path/"status.json")
    job={"external_id":"edge","updated_at":"2026-09-22T11:00:01+00:00"}
    fresh,_,_=freshness.fresh_jobs(
        [job],hours=1,since="2026-09-22T11:00:00+00:00",
        now=datetime(2026,9,22,12,5,tzinfo=timezone.utc),
    )
    assert [x["external_id"] for x in fresh]==["edge"]
