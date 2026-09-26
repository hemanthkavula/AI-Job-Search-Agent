import time
from app import source_health


def test_career_site_health_checks_run_concurrently(monkeypatch,tmp_path):
    source_health.ROOT=tmp_path
    (tmp_path/"sources.json").write_text('{"career_site":[{"company":"A","search_url":"https://a.test/jobs","job_url_pattern":".+"},{"company":"B","search_url":"https://b.test/jobs","job_url_pattern":".+"}]}',encoding="utf-8")
    monkeypatch.setattr(source_health,"load_registry",lambda:{})
    monkeypatch.setattr(source_health,"as_discovery_config",lambda reg:{})
    def slow(company,url,pattern,timeout):
        time.sleep(0.12)
        return {"status":"ok","http_status":200,"matching_job_links":1}
    monkeypatch.setattr(source_health,"validate_career_site",slow)
    started=time.monotonic()
    report=source_health.run("sources.json",timeout=1)
    elapsed=time.monotonic()-started
    assert len([r for r in report["sources"] if r["provider"]=="career_site"])==2
    assert elapsed < 0.22
