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


def test_explicit_relative_posting_age_beats_updated_at(tmp_path, monkeypatch):
    """Regression: Stryker R569401 said Posted 3 Days Ago and must not pass a 24h gate."""
    monkeypatch.setattr(freshness,"STATE",tmp_path/"seen.json")
    monkeypatch.setattr(freshness,"STATUS",tmp_path/"status.json")
    now=datetime(2026,9,24,22,35,tzinfo=timezone.utc)
    job={
        "external_id":"R569401",
        "company":"Stryker",
        "posted_on":"Posted 3 Days Ago",
        "updated_at":"2026-09-24T22:30:00+00:00",
    }
    fresh,stale,_=freshness.fresh_jobs([job],hours=24,now=now)
    assert fresh==[]
    assert [x["external_id"] for x in stale]==["R569401"]
    assert stale[0]["freshness_rejection_reason"]=="outside requested posting window"


def test_relative_posted_today_passes_24h_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(freshness,"STATE",tmp_path/"seen.json")
    monkeypatch.setattr(freshness,"STATUS",tmp_path/"status.json")
    now=datetime(2026,9,24,22,35,tzinfo=timezone.utc)
    job={"external_id":"today","posted_on":"Posted Today","updated_at":"2026-09-20T00:00:00+00:00"}
    fresh,stale,_=freshness.fresh_jobs([job],hours=24,now=now)
    assert [x["external_id"] for x in fresh]==["today"]
    assert stale==[]
    assert fresh[0]["freshness_basis"]=="posted_on"


def test_unparseable_explicit_posting_does_not_fall_back_to_updated_at(tmp_path, monkeypatch):
    monkeypatch.setattr(freshness,"STATE",tmp_path/"seen.json")
    monkeypatch.setattr(freshness,"STATUS",tmp_path/"status.json")
    now=datetime(2026,9,24,22,35,tzinfo=timezone.utc)
    job={"external_id":"unknown","posted_on":"Recently posted","updated_at":"2026-09-24T22:30:00+00:00"}
    fresh,stale,_=freshness.fresh_jobs([job],hours=24,now=now)
    assert fresh==[]
    assert stale[0]["freshness_rejection_reason"]=="missing trustworthy posting timestamp"
