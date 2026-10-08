import json
from pathlib import Path

import pytest
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


def test_title_from_description_recovers_explicit_seeking_role():
    jd = (
        "Eaton's Corporate Sector division is currently seeking a Lead AI and Data Engineer. "
        "As a Lead AI & Data Engineer, you will design, develop, and deploy scalable AI solutions."
    )
    assert manual._title_from_description(jd, "Eaton") == "Lead AI and Data Engineer"


def test_manual_module_routes_authoritative_metadata_through_shared_finalizer():
    source = Path(manual.__file__).read_text(encoding="utf-8")
    assert "enrich_authoritative_job_metadata" in source
    assert "def _workday_detail_metadata" not in source
    assert "job_detail_is_live" not in source


def test_fallback_title_company():
    title, company = manual._fallback_title_company("<title>Senior Data Engineer | Example Corp</title>")
    assert title == "Senior Data Engineer"
    assert company == "Example Corp"


def test_clean_company_removes_portal_suffixes():
    assert manual._clean_company_label("Ford Global Career Site") == "Ford"
    assert manual._clean_company_label("Schwab Jobs") == "Schwab"
    assert manual._clean_company_label("Dayforce Jobs") == ""


def test_aggregator_names_are_not_displayed_as_employers():
    for value in ("Adzuna", "Adzuna US", "Indeed", "ZipRecruiter", "Glassdoor"):
        assert manual._clean_company_label(value) == ""
        assert manual._company_is_aggregator(value) is True


def test_fallback_title_skips_aggregator_brand():
    title, company = manual._fallback_title_company(
        "<title>Senior Data Engineer | Acme Corp | Adzuna</title>"
    )
    assert title == "Senior Data Engineer"
    assert company == "Acme Corp"

    title, company = manual._fallback_title_company(
        "<title>Data Engineer at Example Health - Adzuna</title>"
    )
    assert title == "Data Engineer"
    assert company == "Example Health"


def test_verified_company_prefers_structured_jobposting():
    company, source = manual._verified_company(
        resolved_meta={"company": "Acme Health"},
        initial_meta={"company": "Portal Vendor"},
        provider="greenhouse",
        identifier="acmehealth",
        effective_url="https://boards.greenhouse.io/acmehealth/jobs/1",
        submitted_url="https://example.com/job",
        raw_company="Staffing Portal",
        resolved_site_name="Greenhouse",
        resolved_fallback="Job Details",
        initial_site_name="Example Jobs",
        initial_fallback="Example Jobs",
    )
    assert company == "Acme Health"
    assert source == "resolved_jobposting"


def test_verified_company_uses_ats_tenant_before_portal_brand():
    company, source = manual._verified_company(
        resolved_meta={},
        initial_meta={},
        provider="workday",
        identifier="eaton|Eaton_Careers",
        effective_url="https://eaton.wd5.myworkdayjobs.com/Eaton_Careers/job/1",
        submitted_url="https://example.com/job",
        raw_company="Workday",
        resolved_site_name="Workday",
        resolved_fallback="Job Details",
        initial_site_name="Example Staffing",
        initial_fallback="Example Staffing",
    )
    assert company == "Eaton"
    assert source == "ats_tenant"


def test_verified_company_does_not_guess_from_single_portal_label():
    company, source = manual._verified_company(
        resolved_meta={},
        initial_meta={},
        provider=None,
        identifier=None,
        effective_url="https://jobs.vendor-portal.example/opening/1",
        submitted_url="https://jobs.vendor-portal.example/opening/1",
        raw_company="Vendor Portal",
        resolved_site_name="Staffing Company",
        resolved_fallback="Client Confidential",
        initial_site_name="Different Brand",
        initial_fallback="Another Name",
    )
    assert company == "Company"
    assert source == "unverified"





def test_verified_company_accepts_direct_domain_when_page_agrees():
    company, source = manual._verified_company(
        resolved_meta={},
        initial_meta={},
        provider=None,
        identifier=None,
        effective_url="https://careers.acme.com/jobs/123",
        submitted_url="https://careers.acme.com/jobs/123",
        raw_company="Acme Inc.",
        resolved_site_name="Acme",
        resolved_fallback="Senior Data Engineer | Acme",
        initial_site_name="Acme",
        initial_fallback="Acme",
    )
    assert company in {"Acme", "Acme Inc."}
    assert source == "corroborated_page_metadata"


def test_verified_company_requires_corroboration_when_host_is_ats_or_aggregator():
    company, source = manual._verified_company(
        resolved_meta={},
        initial_meta={},
        provider=None,
        identifier=None,
        effective_url="https://www.indeed.com/viewjob?jk=123",
        submitted_url="https://www.indeed.com/viewjob?jk=123",
        raw_company="Random Staffing",
        resolved_site_name="Indeed",
        resolved_fallback="Client Confidential",
        initial_site_name="Indeed",
        initial_fallback="Another Name",
    )
    assert company == "Company"
    assert source == "unverified"


def test_generic_job_titles_are_not_displayed():
    assert manual._clean_job_title("Job Details") == ""
    assert manual._clean_job_title("Job") == ""
    assert manual._clean_job_title("Senior Data Engineer") == "Senior Data Engineer"


def test_ats_display_exposes_provider_and_clean_tenant():
    label, tenant = manual._ats_display("workday", "unitedhealthgroup|UHG_Careers")
    assert label == "Workday"
    assert tenant == "Unitedhealthgroup"


def test_startup_recovery_requeues_interrupted_structural_and_bad_company(monkeypatch, isolated):
    rows = manual.add_links([
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
        "https://example.com/d",
    ])
    state = manual._load_state()
    state["jobs"][rows[0]["key"]].update({
        "status": "GENERATING_RESUME",
        "company": "Acme",
        "description": "usable",
        "description_usable": True,
    })
    state["jobs"][rows[1]["key"]].update({
        "status": "HOLD_RESUME_ERROR",
        "error": "Fidelity Investments must contain exactly 8 bullets",
        "company": "Beta",
        "description": "usable",
        "description_usable": True,
    })
    state["jobs"][rows[2]["key"]].update({
        "status": "READY_TO_APPLY",
        "company": "Adzuna",
        "description": "",
        "description_usable": False,
        "resume_path": "old.docx",
        "pdf_path": "old.pdf",
    })
    state["jobs"][rows[3]["key"]].update({
        "status": "HOLD_ATS_REVIEW",
        "company": "Walmart Careers",
        "description": "usable",
        "description_usable": True,
        "ats_audit": {
            "quality_gates": {"structure": False},
            "blocking_quality_gates": ["structure"],
        },
    })
    manual._save_state(state)

    started = {}
    class DummyThread:
        def __init__(self, *, target, args, daemon, name):
            started.update({"target": target, "args": args, "daemon": daemon, "name": name})
        def start(self):
            started["started"] = True

    monkeypatch.setattr(manual.threading, "Thread", DummyThread)
    keys = manual._recover_interrupted_jobs()

    assert set(keys) == {row["key"] for row in rows}
    assert started["target"] is manual.process_jobs
    assert started["started"] is True
    fixed = manual._load_state()["jobs"][rows[2]["key"]]
    assert fixed["company"] == ""
    assert fixed["status"] == "PENDING"
    assert fixed["resume_path"] is None
    assert fixed["pdf_path"] is None


def test_terminal_failures_do_not_keep_batch_processing(isolated):
    row = manual.add_links(["https://example.com/a"])[0]
    state = manual._load_state()
    state["jobs"][row["key"]]["status"] = "HOLD_RESUME_ERROR"
    manual._save_state(state)
    listing = manual.api_list()
    assert listing["counts"]["processing"] == 0
    assert listing["counts"]["hidden_terminal"] == 1


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


def test_manual_path_has_no_private_resume_selector_override():
    assert not hasattr(manual, "_manual_should_use_master_resume")


def test_production_selector_honors_manual_force_tailoring_without_changing_default():
    weak = {
        "tailoring_mode": "BASE_RESUME_CONSERVATIVE",
        "description_complete": False,
    }
    assert manual.batch_prepare._should_use_master_resume(weak, {"target_count": 1}) is True

    forced = dict(weak, force_jd_tailoring=True)
    assert manual.batch_prepare._should_use_master_resume(forced, {"target_count": 0}) is False


def test_shared_pipeline_calls_production_prepare(monkeypatch, isolated):
    captured = {}

    def fake_prepare(report, output, external_id=None, limit=None):
        payload = json.loads(Path(report).read_text())
        captured["payload"] = payload
        captured["external_id"] = external_id
        captured["draft"] = manual.batch_prepare.DRAFT_RESUME_DIR
        captured["final"] = manual.batch_prepare.FINAL_RESUME_DIR
        captured["selector"] = manual.batch_prepare._should_use_master_resume
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
    assert captured["selector"] is manual.batch_prepare._should_use_master_resume


def test_add_links_persists_separate_manual_state(isolated):
    rows = manual.add_links(["https://example.com/1", "https://example.com/2"])
    assert len(rows) == 2
    assert manual.STATE_FILE.exists()
    assert manual.STATE_FILE.parent.name == "manual_job_links"
    assert len(manual._load_state()["jobs"]) == 2


def test_reset_manual_state_deletes_only_manual_tree(isolated):
    rows = manual.add_links(["https://example.com/1", "https://example.com/2"])
    assert len(rows) == 2
    manual.WORK_DIR.mkdir(parents=True, exist_ok=True)
    manual.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (manual.WORK_DIR / "scratch.txt").write_text("x")
    (manual.ARTIFACT_DIR / "resume.pdf").write_bytes(b"x")
    sibling = manual.STATE_DIR / "normal_pipeline.json"
    sibling.parent.mkdir(parents=True, exist_ok=True)
    sibling.write_text("keep")

    deleted = manual.reset_manual_state()

    assert deleted == 2
    assert manual._load_state()["jobs"] == {}
    assert not (manual.WORK_DIR / "scratch.txt").exists()
    assert not (manual.ARTIFACT_DIR / "resume.pdf").exists()
    assert sibling.read_text() == "keep"


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


def test_process_job_cleans_stale_portal_company_before_resume(monkeypatch, isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    raw = _usable_raw("https://example.com/1")
    raw["company"] = "Walmart Careers"
    raw["company_key"] = "Walmart Careers"
    monkeypatch.setattr(manual, "fetch_manual_job", lambda url: raw)
    seen = {}
    monkeypatch.setattr(manual, "run_shared_resume_pipeline", lambda value: (
        seen.update(value) or {
            "next_action": "READY_TO_APPLY",
            "resume_path": None,
            "pdf_path": None,
        }
    ))
    got = manual.process_job(row["key"])
    assert got["company"] == "Walmart"
    assert seen["company"] == "Walmart"
    assert seen["company_key"] == "Walmart"
    assert seen["force_jd_tailoring"] is True


def test_partial_manual_jd_is_not_sent_to_resume_pipeline(monkeypatch, isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    state = manual._load_state()
    state["jobs"][row["key"]].update({
        "company": "Edited Co", "title": "Data Engineer", "description": "pasted jd",
        "description_usable": True, "description_complete": False, "tailoring_mode": "BASE_RESUME_CONSERVATIVE",
    })
    manual._save_state(state)
    monkeypatch.setattr(manual, "fetch_manual_job", lambda url: pytest.fail("should not refetch edited JD"))
    monkeypatch.setattr(
        manual,
        "run_shared_resume_pipeline",
        lambda raw: pytest.fail("partial manual JD must not generate a resume"),
    )
    got = manual.process_job(row["key"])
    assert got["status"] == "IGNORED_INCOMPLETE_JD"
    assert manual._load_state()["jobs"][row["key"]]["ignore_reason"]


def test_blocked_page_with_no_usable_jd_is_ignored(monkeypatch, isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    monkeypatch.setattr(manual, "_fetch_public_page", lambda url: None)
    monkeypatch.setattr(manual, "resolve_original_ats", lambda job: job)
    monkeypatch.setattr(manual, "resolve_full_jd", lambda job: job)
    monkeypatch.setattr(manual, "_looks_like_complete_jd", lambda text, source="": False)
    monkeypatch.setattr(manual, "_looks_like_usable_jd", lambda text, source="": False)
    monkeypatch.setattr(manual, "detect_ats", lambda url: (None, None))
    monkeypatch.setattr(
        manual,
        "run_shared_resume_pipeline",
        lambda raw: pytest.fail("no-JD link must not enter the resume pipeline"),
    )

    got = manual.process_job(row["key"])
    assert got["status"] == "IGNORED_NO_JD"
    stored = manual._load_state()["jobs"][row["key"]]
    assert stored["next_action"] == "IGNORED_NO_JD"
    assert stored["description_usable"] is False
    assert not stored.get("resume_path")
    assert not stored.get("pdf_path")


def test_generic_job_title_is_ignored_even_with_complete_jd(monkeypatch, isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    raw = _usable_raw("https://example.com/1")
    raw.update({
        "title": "Job opening",
        "title_verified": False,
        "company_verified": True,
        "description_complete": True,
        "description_usable": True,
    })
    monkeypatch.setattr(manual, "fetch_manual_job", lambda url: raw)
    monkeypatch.setattr(
        manual,
        "run_shared_resume_pipeline",
        lambda value: pytest.fail("generic-title job must not generate a resume"),
    )
    got = manual.process_job(row["key"])
    assert got["status"] == "IGNORED_INCOMPLETE_JOB"
    assert "title" in got["ignore_reason"].lower()


def test_unverified_company_is_ignored_even_with_complete_jd(monkeypatch, isolated):
    row = manual.add_links(["https://example.com/1"])[0]
    raw = _usable_raw("https://example.com/1")
    raw.update({
        "company": "Company",
        "company_key": "Company",
        "company_verified": False,
        "title_verified": True,
        "description_complete": True,
        "description_usable": True,
    })
    monkeypatch.setattr(manual, "fetch_manual_job", lambda url: raw)
    monkeypatch.setattr(
        manual,
        "run_shared_resume_pipeline",
        lambda value: pytest.fail("unverified-company job must not generate a resume"),
    )
    got = manual.process_job(row["key"])
    assert got["status"] == "IGNORED_INCOMPLETE_JOB"
    assert "employer" in got["ignore_reason"].lower()


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


def test_api_functions_add_and_list_without_http_client(isolated):
    background = manual.BackgroundTasks()
    added = manual.api_add(
        manual.LinksInput(links="https://example.com/a\nhttps://example.com/b"),
        background,
    )
    assert added["ok"] is True
    assert added["queued"] == 2
    assert len(background.tasks) == 1
    listing = manual.api_list()
    assert listing["jobs"] == []
    assert listing["counts"]["total"] == 2
    assert listing["counts"]["processing"] == 2
    assert listing["current"] is not None


def test_ignored_no_jd_is_hidden_from_ready_queue(isolated):
    row = manual.add_links(["https://example.com/no-jd"])[0]
    state = manual._load_state()
    state["jobs"][row["key"]]["status"] = "IGNORED_NO_JD"
    state["jobs"][row["key"]]["next_action"] = "IGNORED_NO_JD"
    manual._save_state(state)

    listing = manual.api_list()
    assert listing["jobs"] == []
    assert listing["counts"]["processing"] == 0
    assert listing["counts"]["hidden_terminal"] == 1


def test_api_list_shows_only_ready_or_applied_rows(isolated):
    rows = manual.add_links(["https://example.com/a", "https://example.com/b", "https://example.com/c"])
    state = manual._load_state()
    state["jobs"][rows[0]["key"]]["status"] = "READY_TO_APPLY"
    state["jobs"][rows[1]["key"]]["status"] = "HOLD_RESUME_ERROR"
    state["jobs"][rows[2]["key"]]["status"] = "READY_TO_APPLY"
    state["jobs"][rows[2]["key"]]["application_status"] = "SUBMITTED_CONFIRMED"
    manual._save_state(state)

    listing = manual.api_list()
    assert {x["key"] for x in listing["jobs"]} == {rows[0]["key"], rows[2]["key"]}
    assert listing["counts"]["ready"] == 1
    assert listing["counts"]["applied"] == 1
    assert listing["counts"]["total"] == 3
    assert listing["counts"]["processing"] == 0
    assert listing["counts"]["hidden_terminal"] == 1


def test_add_rejects_bad_url_without_http_client(isolated):
    with pytest.raises(Exception) as exc:
        manual.api_add(
            manual.LinksInput(links="http://127.0.0.1/job"),
            manual.BackgroundTasks(),
        )
    assert getattr(exc.value, "status_code", None) == 400


def test_manual_page_has_required_controls():
    assert "Manual Job Links" in manual.MANUAL_PAGE
    assert "Job Discovery" in manual.MANUAL_PAGE
    assert "Add & Process" in manual.MANUAL_PAGE
    assert "Processing" in manual.MANUAL_PAGE
    assert "Mark Applied" in manual.MANUAL_PAGE
    assert "View Resume" in manual.MANUAL_PAGE
    assert "Delete" in manual.MANUAL_PAGE
    assert "Regenerate" not in manual.MANUAL_PAGE
    assert "Process / Retry" not in manual.MANUAL_PAGE


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
