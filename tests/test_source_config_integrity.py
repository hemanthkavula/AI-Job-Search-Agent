import json
from pathlib import Path

CONFIG=Path("data/job_sources.json")

def test_talentreef_sources_are_client_scoped_or_verified_public_tenants():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"))
    for provider in ("talentreef","jobappnetwork"):
        for src in cfg.get(provider,[]):
            client_id=src.get("client_id") or src.get("clientId")
            search_url=(src.get("search_url") or "").lower()
            verified_public_tenant=search_url.startswith("https://apply.jobappnetwork.com/")
            assert client_id or verified_public_tenant, (
                f"{provider} source {src.get('company')} needs client_id or verified JobAppNetwork tenant URL"
            )

def test_source_config_has_no_duplicate_urls_within_provider():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"))
    for provider,rows in cfg.items():
        if not isinstance(rows,list):
            continue
        urls=[]
        for src in rows:
            if not isinstance(src,dict):
                continue
            url=src.get("search_url") or src.get("base_url") or src.get("careers_url") or src.get("original_url")
            if url: urls.append(url.rstrip("/").lower())
        assert len(urls)==len(set(urls)), f"duplicate URLs configured for {provider}"


def test_ashby_collector_url_encodes_learned_board_names(monkeypatch):
    import json
    from app.sources import ashby
    captured={}
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self):return json.dumps({"jobs":[]}).encode()
    def fake_urlopen(req,timeout=20):
        captured["url"]=req.full_url
        return Response()
    monkeypatch.setattr(ashby,"urlopen",fake_urlopen)
    assert ashby.fetch_jobs("superhuman platform inc")==[]
    assert "superhuman%20platform%20inc" in captured["url"]
    assert " " not in captured["url"]
