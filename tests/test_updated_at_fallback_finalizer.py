import json
from datetime import datetime, timezone

import app.jd_finalizer as finalizer


def _report(tmp_path):
    url="https://boards.greenhouse.io/acme/jobs/123"
    report={
        "results":[{
            "action":"ELIGIBLE_FOR_RESUME",
            "job":{
                "external_id":"greenhouse:acme:123",
                "source":"greenhouse",
                "company_key":"Acme",
                "title":"Senior Data Engineer",
                "location":"Remote - US",
                "url":url,
                "original_url":url,
                "ats_provider":"greenhouse",
                "freshness_basis":"updated_at_fallback",
                "updated_at":"2026-10-03T12:30:00+00:00",
                "description":"data pipelines etl spark warehouse requirements responsibilities",
                "description_usable":True,
            },
        }]
    }
    path=tmp_path/"eligible.json"
    path.write_text(json.dumps(report),encoding="utf-8")
    return path


def _patch_common(monkeypatch):
    monkeypatch.setattr(finalizer,"load_profile",lambda :{})
    monkeypatch.setattr(finalizer,"resolve_full_jd",lambda job:dict(job))


def test_updated_at_fallback_requires_official_post_date_and_rejects_stale(tmp_path, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(finalizer,"_fetch_public_page",lambda url:'<html><script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-10-01T12:00:00Z"}</script></html>')
    result=finalizer.finalize_report(
        _report(tmp_path),output_path=tmp_path/"final.json",hours=24,
        now=datetime(2026,10,3,13,0,tzinfo=timezone.utc),
    )
    assert result["finalized"]==0
    assert result["rejections"][0]["action"]=="REJECT_STALE_OFFICIAL_POSTING"


def test_updated_at_fallback_holds_when_official_post_date_cannot_be_verified(tmp_path, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(finalizer,"_fetch_public_page",lambda url:"<html><body>Careers</body></html>")
    result=finalizer.finalize_report(
        _report(tmp_path),output_path=tmp_path/"final.json",hours=24,
        now=datetime(2026,10,3,13,0,tzinfo=timezone.utc),
    )
    assert result["finalized"]==0
    assert result["rejections"][0]["action"]=="HOLD_OFFICIAL_POST_DATE_UNVERIFIED"
    assert "modification timestamp" in result["rejections"][0]["reason"]


def test_finalizer_uses_job_source_freshness_cutoff_not_broad_global_window(tmp_path, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(finalizer,"_fetch_public_page",lambda url:'<html><script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-10-03T09:00:00Z"}</script></html>')
    monkeypatch.setattr(finalizer,"_live_public_job_page",lambda url:(True,"reachable"))
    monkeypatch.setattr(finalizer,"two_category_filter",lambda job,profile:{"eligible":True})
    monkeypatch.setattr(finalizer,"passes_hard_filters",lambda job,profile:(True,[]))
    report_path=_report(tmp_path)
    payload=json.loads(report_path.read_text(encoding="utf-8"))
    payload["results"][0]["job"]["freshness_cutoff"]="2026-10-03T10:00:00Z"
    report_path.write_text(json.dumps(payload),encoding="utf-8")
    result=finalizer.finalize_report(
        report_path,output_path=tmp_path/"final_source_cutoff.json",hours=183,
        now=datetime(2026,10,3,13,0,tzinfo=timezone.utc),
    )
    assert result["finalized"]==0
    assert result["rejections"][0]["action"]=="REJECT_STALE_OFFICIAL_POSTING"
    assert result["rejections"][0]["diagnostics"]["freshness_cutoff"]=="2026-10-03T10:00:00+00:00"
