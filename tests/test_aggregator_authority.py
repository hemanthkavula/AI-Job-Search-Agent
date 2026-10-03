import json

import pytest

import app.jd_finalizer as jd_finalizer


@pytest.mark.parametrize(
    "url",
    [
        "https://www.dice.com/job-detail/123",
        "https://www.ziprecruiter.com/jobs/example",
        "https://www.indeed.com/viewjob?jk=123",
        "https://www.linkedin.com/jobs/view/123",
        "https://www.monster.com/job-openings/example",
        "https://wellfound.com/jobs/123-data-engineer",
        "https://builtin.com/job/data/data-engineer/123",
        "https://www.ycombinator.com/companies/example/jobs/abc-data-engineer",
        "https://www.workatastartup.com/jobs/12345",
    ],
)
def test_all_discovery_board_hosts_are_aggregators(url):
    assert jd_finalizer._is_aggregator_url(url)


def test_employer_ats_host_is_not_aggregator():
    assert not jd_finalizer._is_aggregator_url("https://boards.greenhouse.io/example/jobs/123")
    assert not jd_finalizer._is_aggregator_url("https://example.wd5.myworkdayjobs.com/en-US/jobs/job/123")


@pytest.mark.parametrize("source,host", [
    ("wellfound", "https://wellfound.com/jobs/123"),
    ("builtin", "https://builtin.com/job/data/data-engineer/123"),
    ("yc_jobs", "https://www.ycombinator.com/companies/example/jobs/123"),
])
def test_unresolved_public_portal_leads_are_held_before_resume_work(monkeypatch,tmp_path,source,host):
    job={
        "external_id":f"{source}:123",
        "source":source,
        "company_key":"Example Co",
        "title":"Data Engineer",
        "location":"Remote - US",
        "employment_type":"Full-Time",
        "url":host,
        "original_url":host,
        "description":"Responsibilities: build data pipelines. Requirements: Python SQL Spark. Qualifications: 5 years experience.",
        "description_complete":True,
        "description_usable":True,
        "discovery_only":True,
    }
    report={"results":[{"action":"ELIGIBLE_FOR_RESUME","job":job}]}
    report_path=tmp_path/"eligible.json"
    output_path=tmp_path/"finalized.json"
    report_path.write_text(json.dumps(report),encoding="utf-8")

    # Model the unresolved outcome of canonicalization. The finalizer must hold
    # the board URL immediately, before live-page or paid-resume work.
    monkeypatch.setattr(jd_finalizer,"resolve_full_jd",lambda raw:dict(raw))
    monkeypatch.setattr(jd_finalizer,"load_profile",lambda:{})
    monkeypatch.setattr(
        jd_finalizer,
        "_live_public_job_page",
        lambda url: (_ for _ in ()).throw(AssertionError("board URL reached live employer check")),
    )

    result=jd_finalizer.finalize_report(str(report_path),str(output_path))
    assert result["finalized"] == 0
    assert result["held_or_rejected"] == 1
    assert result["rejections"][0]["action"] == "HOLD_ATS_UNRESOLVED"


def test_public_portal_source_set_is_complete_for_enabled_portals():
    assert {"dice","ziprecruiter","wellfound","builtin","yc_jobs"}.issubset(jd_finalizer.AGGREGATOR_SOURCES)
