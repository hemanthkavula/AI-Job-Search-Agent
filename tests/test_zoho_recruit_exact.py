import json
from app.sources import zoho_recruit


def test_zoho_embedded_js_payload_recovers_full_job():
    description="<p>Responsibilities: Build and maintain reliable SQL data pipelines with Python, dbt and GCP.</p>" * 6
    payload=json.dumps([{"Posting_Title":"Data Integration & Data Quality Engineer","Job_Description":description,"City":"McKinney"}])
    encoded=payload.replace('"',r"\x22")
    page="<script>var jobs = JSON.parse('"+encoded+"');</script>"
    jobs=zoho_recruit._embedded_jobs(page)
    assert len(jobs)==1
    assert jobs[0]["Posting_Title"]=="Data Integration & Data Quality Engineer"
    assert len(jobs[0]["Job_Description"])>180


def test_zoho_js_escape_decoder_preserves_nested_quotes():
    assert zoho_recruit._decode_js_literal(r'\\\x22') == r'\"'
    assert zoho_recruit._decode_js_literal(r'\x26') == "&"


def test_zoho_rejects_non_job_url():
    assert zoho_recruit.fetch_job("Example","https://example.com/jobs/123") is None
