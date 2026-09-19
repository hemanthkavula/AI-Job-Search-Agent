from app.application_navigator import provider_from_url, APPLY_RE, FINAL_RE

def test_provider_detection_covers_supported_ats():
    assert provider_from_url("https://careers.example.icims.com/jobs/1/job") == "icims"
    assert provider_from_url("https://boards.greenhouse.io/acme/jobs/1") == "greenhouse"
    assert provider_from_url("https://jobs.lever.co/acme/1") == "lever"
    assert provider_from_url("https://jobs.ashbyhq.com/acme/1") == "ashby"
    assert provider_from_url("https://acme.myworkdayjobs.com/job/1") == "workday"
    assert provider_from_url("https://jobs.smartrecruiters.com/acme/1") == "smartrecruiters"
    assert provider_from_url("https://jobs.jobvite.com/acme/job/1") == "jobvite"
    assert provider_from_url("https://www.dice.com/job-detail/1") == "dice"

def test_apply_entry_never_matches_final_submit_as_safe_entry():
    assert APPLY_RE.search("Apply Now")
    assert FINAL_RE.search("Submit Application")
    assert FINAL_RE.search("Submit")
