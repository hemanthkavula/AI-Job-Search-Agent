import json
from http.client import IncompleteRead
from urllib.error import URLError

from app import discovery, source_health
from app.sources import icims, ukg, ziprecruiter


class _Response:
    status=200
    def __init__(self, body=b"<html>ok</html>"):
        self.body=body
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self):
        return self.body


def test_ukg_retries_incomplete_read(monkeypatch):
    calls=[]
    def fake_open(request, timeout=0):
        calls.append(request.full_url)
        if len(calls)==1:
            raise IncompleteRead(b"partial", 20)
        return _Response(b"<html>recovered</html>")
    monkeypatch.setattr(ukg,"urlopen",fake_open)
    monkeypatch.setattr(ukg.time,"sleep",lambda *_:None)
    body=ukg._get("https://example.test/jobs",timeout=1,retries=2)
    assert "recovered" in body
    assert len(calls)==2


def test_icims_encodes_unicode_url_before_request(monkeypatch):
    seen=[]
    def fake_open(request, timeout=0):
        seen.append(request.full_url)
        return _Response()
    monkeypatch.setattr(icims,"urlopen",fake_open)
    icims._get("https://example.test/jobs/Data–Engineer",timeout=1,retries=1)
    assert seen
    assert "–" not in seen[0]
    assert "%E2%80%93" in seen[0]


def test_source_health_retries_transient_probe(monkeypatch):
    calls=[]
    def fake_open(request, timeout=0):
        calls.append(request.full_url)
        if len(calls)==1:
            raise URLError("temporary")
        return _Response()
    monkeypatch.setattr(source_health,"urlopen",fake_open)
    monkeypatch.setattr(source_health.time,"sleep",lambda *_:None)
    result=source_health._probe("https://example.test/jobs",timeout=1,retries=2)
    assert result["status"]=="ok"
    assert result["attempts"]==2


def test_ziprecruiter_keeps_results_when_one_query_fails(monkeypatch):
    monkeypatch.setattr(ziprecruiter,"SEARCH_TERMS",("Data Engineer","Senior Data Engineer"))
    monkeypatch.setattr(ziprecruiter,"OFFSETS",(0,))
    calls=[]
    def fake_call(url,tool,args):
        calls.append(args["keyword"])
        if args["keyword"]=="Data Engineer":
            raise RuntimeError("temporary MCP error")
        return {"jobs":[{
            "id":"job-1",
            "title":"Senior Data Engineer",
            "company":"Example",
            "location":"New York, NY",
            "employment_type":"full_time",
            "url":"https://example.test/job/1",
            "posted_at":"2026-10-07T12:00:00Z",
        }]}
    monkeypatch.setattr(ziprecruiter,"call_tool",fake_call)
    rows=ziprecruiter.fetch_jobs()
    assert calls==["Data Engineer","Senior Data Engineer"]
    assert len(rows)==1
    assert rows[0]["company_key"]=="Example"


def test_discovery_retries_transiently_unhealthy_ats(monkeypatch,tmp_path):
    health_path=tmp_path/"source_health.json"
    health_path.write_text(json.dumps({
        "sources":[{
            "provider":"greenhouse",
            "company":"Example Co",
            "status":"unreachable",
            "target":"https://example.test",
        }]
    }),encoding="utf-8")
    job={
        "external_id":"greenhouse:1",
        "source":"greenhouse",
        "company_key":"Example Co",
        "title":"Data Engineer",
        "url":"https://example.test/job/1",
        "description":"Python SQL data pipelines",
        "posted_at":"2026-10-07T12:00:00Z",
    }
    monkeypatch.setattr(discovery,"greenhouse_jobs",lambda token:[job])
    monkeypatch.setattr(discovery,"load_registry",lambda *a,**k:{})
    monkeypatch.setattr(discovery,"as_discovery_config",lambda reg:{})
    monkeypatch.setattr(discovery,"learn_from_jobs",lambda jobs,reg:[])
    monkeypatch.setattr(discovery,"save_registry",lambda *a,**k:None)
    monkeypatch.setattr(discovery,"load_company_registry",lambda:{})
    monkeypatch.setattr(discovery,"learn_companies_from_jobs",lambda *a,**k:None)
    monkeypatch.setattr(discovery,"save_company_registry",lambda *a,**k:None)
    monkeypatch.setattr(discovery,"annotate_jobs",lambda rows:rows)

    rows,errors,coverage=discovery.discover(
        {"greenhouse":[{"company":"Example Co","board_token":"example"}]},
        only_source="greenhouse",
        health_path=str(health_path),
        return_coverage=True,
    )
    assert errors==[]
    assert len(rows)==1
    assert coverage["successful_units"]==1
    persisted=json.loads(health_path.read_text(encoding="utf-8"))
    assert persisted["greenhouse:Example Co"]["status"]=="OK"
