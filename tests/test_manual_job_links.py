import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.manual_job_links as manual


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    root = tmp_path / "state"
    monkeypatch.setattr(manual, "STATE_DIR", root)
    monkeypatch.setattr(manual, "MANUAL_DIR", root / "manual_job_links")
    monkeypatch.setattr(manual, "STATE_FILE", root / "manual_job_links" / "manual_jobs.json")
    monkeypatch.setattr(manual, "WORK_DIR", root / "manual_job_links" / "work")
    monkeypatch.setattr(manual, "ARTIFACT_DIR", root / "manual_job_links" / "resumes")
    return root


def _usable_raw(url="https://jobs.example.com/123"):
    key = manual._key_for_url(url)
    return {
        "external_id": key,
        "source": "greenhouse",
        "company_key": "Example Co",
        "company": "Example Co",
        "title": "Senior Data Engineer",
        "description": "Responsibilities build data pipelines. Requirements Python SQL Spark AWS. Qualifications five years experience.",
        "location": "New York, NY",
        "employment_type": "FULL_TIME",
        "url": url,
        "original_url": url,
        "submitted_url": url,
        "description_complete": True,
        "description_usable": True,
        "tailoring_mode": "FULL_JD",
        "manual_link": True,
        "manual_filters_bypassed": True,
        "application_route": "MANUAL_LINK",
    }


def test_normalize_url_strips_fragment():
    assert manual._normalize_url("HTTPS://Example.COM/jobs/1?a=2#apply") == "https://example.com/jobs/1?a=2"


@pytest.mark.parametrize("url", ["ftp://example.com/x", "javascript:alert(1)", "not-a-url"])
def test_rejects_non_http_urls(url):
    with pytest.raises(ValueError):
        manual._normalize_url(url)


@pytest.mark.parametrize("url", ["http://localhost/job", "http://127.0.0.1/job", "http://10.1.2.3/job"])
def test_rejects_local_private_urls(url):
    with pytest.raises(ValueError):
        manual._normalize_url(url)


def test_split_links_deduplicates():
    assert manual._split_links("https://example.com/a\nhttps://example.com/a#x\nhttps://example.com/b") == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_key_is_stable_across_fragment():
    assert manual._key_for_url("https://example.com/a#x") == manual._key_for_url("https://example.com/a")


def test_jsonld_metadata_extracts_job_fields():
    page = """<script type="application/ld+json">{
      "@context":"https://schema.org","@type":"JobPosting",
      "title":"Data Engineer","description":"<p>Build pipelines with Python and SQL.</p>",
      "datePosted":"2026-10-07","employmentType":"FULL_TIME",
      "identifier":{"value":"REQ-1"},
      "hiringOrganization":{"@type":"Organization","name":"Acme"},
      "jobLocation":{"@type":"Place","address":{"addressLocality":"New York","addressRegion":"NY","addressCountry":"US"}}
    }</script>"""
    got = manual._jsonld_metadata(page)
    assert got["title"] == "Data Engineer"
    assert got["company"] == "Acme"
    assert got["requisition_id"] == "REQ-1"
    assert "New York" in got["location"]
    assert "Build pipelines" in got["description"]


def test_fallback_title_company():
    title, company = manual._fallback_title_company("<title>Senior Data Engineer | Example Corp</title>")
    assert title == "Senior Data Engineer"
    assert company == "Example Corp"


def test_fetch_manual_job_does_not_run_discovery_filters(monkeypatch):
    page = """<html><head><title>Data Engineer | Acme</title></head><body>
    <h2>Responsibilities</h2><p>Build scalable data pipelines using Python, SQL, Spark and AWS.</p>
    <h2>Requirements</h2><p>Five years data engineering experience.</p></body></html>"""
    monkeypatch.setattr(manual, "_fetch_public_page", lambda url: page)
    monkeypatch.setattr(manual, "resolve_original_ats", lambda job: job)
    monkeypatch.setattr(manual, "resolve_full_jd", lambda job: job)
    monkeypatch.setattr(manual, "_looks_like_complete_jd", lambda text, source="": True)
    monkeypatch.setattr(manual, "_looks_like_usable_jd", lambda text, source="": True)
    monkeypatch.setattr(manual, "detect_ats", lambda url: ("greenhouse", "acme"))
    got = manual.fetch_manual_job("https://jobs.example.com/123")
    assert got["manual_filters_bypassed"] is True
    assert got["application_route"] == "MANUAL_LINK"
    assert got["source"] == "greenhouse"
    assert got["tailoring_mode"] == "FULL_JD"


def test_fetch_manual_job_uses_conservative_mode_for_partial_jd(monkeypatch):
    monkeypatch.setattr(manual, "_fetch_public_page", lambda url: "<title>Data Engineer | Acme</title><p>JD</p>")
    monkeypatch.setattr(manual, "resolve_original_ats", lambda job: job)
    monkeypatch.setattr(manual, "resolve_full_jd", lambda job: job)
    monkeypatch.setattr(manual, "_looks_like_complete_jd", lambda text, source="": False)
    monkeypatch.setattr(manual, "_looks_like_usable_jd", lambda text, source="": True)
    monkeypatch.setattr(manual, "detect_ats", lambda url: (None, None))
    got = manual.fetch_manual_job("https://example.com/job")
    assert got["tailoring_mode"] == "BASE_RESUME_CONSERVATIVE"


def test_bypass_eligibility_is_explicit():
    got = manual._bypass_eligibility()
    assert got["eligible"] is True
    assert got["experience"]["status"] == "BYPASSED_MANUAL_LINK"
    assert got["sponsorship"]["status"] == "BYPASSED_MANUAL_LINK"


def test_shared_pipeline_calls_production_prepare(monkeypatch, isolated):
    captured = {}

    def fake_prepare(report, output, external_id=None, limit=None):
        payload = json.loads(Path(report).read_text())
        captured["payload"] = payload
        captured["external_id"] = external_id
        captured["draft"] = manual.batch_prepare.DRAFT_RESUME_DIR
        captured["final"] = manual.batch_prepare.FINAL_RESUME_DIR
        return [{"next_action": "READY_TO_APPLY", "pdf_path": None, "resume_path": None}]

    monkeypatch.setattr(manual.batch_prepare, "prepare", fake_prepare)
    raw = _usable_raw()
    result = manual.run_shared_resume_pipeline(raw)
    item = captured["payload"]["results"][0]
    assert result["next_action"] == "READY_TO_APPLY"
    assert item["action"] == "FINAL_JD_VERIFIED"
    assert item["job"]["description"] == raw["description"]
    assert item["eligibility"]["manual_bypass"] is True
    assert captured["external_id"] == raw["external_id"]
    assert "manual_job_links" in captured["draft"]
    assert "manual_job_links" in captured["final"]


def test_add_links_persists_separate_manual_state(isolated):
    rows = manual.add_links(["https://example.com/1", "https://example.com/2"])
    assert len(rows) == 2
    assert manual.STATE_FILE.exists()
    assert manual.STATE_FILE.parent.name == "manual_job_links"
    assert len(manual._load_state()["jobs"]) == 2


def test_duplicate_link_does_not_duplicate_or_reset(isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    manual.confirm_submitted(row["key"])
    again = manual.add_links(["https://example.com/1"])[0]
    assert len(manual._load_state()["jobs"]) == 1
    assert again["application_status"] == "SUBMITTED_CONFIRMED"


def test_public_row_hides_jd_text(isolated):
    row = {"key": "manual:x", "description": "secret jd", "pdf_path": None}
    assert "description" not in manual._public(row)


def test_edit_description_makes_job_retryable(monkeypatch, isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    monkeypatch.setattr(manual, "_looks_like_complete_jd", lambda text, source="": True)
    monkeypatch.setattr(manual, "_looks_like_usable_jd", lambda text, source="": True)
    got = manual.edit_job(row["key"], manual.ManualEdit(description="Responsibilities and requirements Python SQL Spark"))
    assert got["status"] == "JD_READY"
    stored = manual._load_state()["jobs"][row["key"]]
    assert stored["description_usable"] is True
    assert stored["tailoring_mode"] == "FULL_JD"


def test_edit_url_resets_fetched_jd(isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    state = manual._load_state()
    state["jobs"][row["key"]].update({"description": "old", "description_usable": True})
    manual._save_state(state)
    got = manual.edit_job(row["key"], manual.ManualEdit(url="https://example.com/2"))
    assert got["status"] == "PENDING"
    stored = manual._load_state()["jobs"][row["key"]]
    assert stored["description"] == ""
    assert stored["submitted_url"] == "https://example.com/2"


def test_process_fetched_job_uses_shared_pipeline(monkeypatch, isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    monkeypatch.setattr(manual, "fetch_manual_job", lambda url: _usable_raw(url))
    monkeypatch.setattr(manual, "run_shared_resume_pipeline", lambda raw: {
        "next_action": "READY_TO_APPLY", "resume_path": None, "pdf_path": None,
        "resume_tailoring_policy": {"mode": "JD_TAILORED"}, "ats_audit": {"passed": True},
        "artifact_validation": {"passed": True},
    })
    got = manual.process_job(row["key"])
    assert got["status"] == "READY_TO_APPLY"
    assert got["company"] == "Example Co"
    assert manual._load_state()["jobs"][row["key"]]["description"]


def test_process_manual_jd_does_not_refetch(monkeypatch, isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    state = manual._load_state()
    state["jobs"][row["key"]].update({
        "company": "Edited Co", "title": "Data Engineer", "description": "pasted jd",
        "description_usable": True, "description_complete": False, "tailoring_mode": "BASE_RESUME_CONSERVATIVE",
    })
    manual._save_state(state)
    monkeypatch.setattr(manual, "fetch_manual_job", lambda url: pytest.fail("should not refetch edited JD"))
    seen = {}
    def fake_pipeline(raw):
        seen.update(raw)
        return {"next_action": "READY_TO_APPLY", "resume_path": None, "pdf_path": None}
    monkeypatch.setattr(manual, "run_shared_resume_pipeline", fake_pipeline)
    manual.process_job(row["key"])
    assert seen["description"] == "pasted jd"
    assert seen["company_key"] == "Edited Co"


def test_fetch_failure_becomes_editable_attention_state(monkeypatch, isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    monkeypatch.setattr(manual, "fetch_manual_job", lambda url: (_ for _ in ()).throw(RuntimeError("blocked")))
    got = manual.process_job(row["key"])
    assert got["status"] == "JD_FETCH_FAILED"
    assert "blocked" in got["error"]


def test_resume_failure_preserves_jd_for_retry(monkeypatch, isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    monkeypatch.setattr(manual, "fetch_manual_job", lambda url: _usable_raw(url))
    monkeypatch.setattr(manual, "run_shared_resume_pipeline", lambda raw: (_ for _ in ()).throw(RuntimeError("renderer failed")))
    got = manual.process_job(row["key"])
    assert got["status"] == "HOLD_RESUME_ERROR"
    stored = manual._load_state()["jobs"][row["key"]]
    assert stored["description_usable"] is True
    assert stored["description"]


def test_mark_applied_is_manual_queue_only(isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    got = manual.confirm_submitted(row["key"])
    assert got["application_status"] == "SUBMITTED_CONFIRMED"
    assert got["submitted_at"]


def test_delete_removes_only_manual_artifacts(isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    safe = manual._safe_key(row["key"])
    (manual.ARTIFACT_DIR / safe).mkdir(parents=True)
    (manual.ARTIFACT_DIR / safe / "resume.pdf").write_bytes(b"x")
    got = manual.delete_job(row["key"])
    assert got["deleted"] is True
    assert not (manual.ARTIFACT_DIR / safe).exists()
    assert row["key"] not in manual._load_state()["jobs"]


def test_api_add_and_list(isolated):
    app = FastAPI()
    app.include_router(manual.router)
    client = TestClient(app)
    response = client.post("/api/manual-links", json={"links": "https://example.com/a\nhttps://example.com/b"})
    assert response.status_code == 200
    listing = client.get("/api/manual-links").json()
    assert listing["counts"]["total"] == 2


def test_api_rejects_bad_url(isolated):
    app = FastAPI()
    app.include_router(manual.router)
    client = TestClient(app)
    response = client.post("/api/manual-links", json={"links": "http://127.0.0.1/job"})
    assert response.status_code == 400


def test_manual_page_has_required_controls():
    assert "Manual Job Links" in manual.MANUAL_PAGE
    assert "Job Discovery" in manual.MANUAL_PAGE
    assert "Add & Process" in manual.MANUAL_PAGE
    assert "Process / Retry" in manual.MANUAL_PAGE
    assert "Mark Applied" in manual.MANUAL_PAGE
    assert "View Resume" in manual.MANUAL_PAGE
    assert "Delete" in manual.MANUAL_PAGE
    assert "Edit" in manual.MANUAL_PAGE


def test_manual_module_does_not_import_discovery_or_filters():
    source = Path(manual.__file__).read_text(encoding="utf-8")
    assert "from app.discovery" not in source
    assert "from app.filters" not in source
    assert "from app.eligibility" not in source
    assert "daily_runner.run" not in source


def test_artifacts_live_below_manual_directory(isolated):
    assert manual.MANUAL_DIR in manual.ARTIFACT_DIR.parents
    assert manual.MANUAL_DIR in manual.WORK_DIR.parents


def test_applied_marker_survives_regeneration(monkeypatch, isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    manual.confirm_submitted(row["key"])
    state = manual._load_state()
    state["jobs"][row["key"]].update({
        "company": "Example Co", "title": "Data Engineer", "description": "manual jd",
        "description_usable": True, "description_complete": False, "tailoring_mode": "BASE_RESUME_CONSERVATIVE",
    })
    manual._save_state(state)
    monkeypatch.setattr(manual, "run_shared_resume_pipeline", lambda raw: {
        "next_action": "READY_TO_APPLY", "resume_path": None, "pdf_path": None,
    })
    got = manual.process_job(row["key"])
    assert got["application_status"] == "SUBMITTED_CONFIRMED"
