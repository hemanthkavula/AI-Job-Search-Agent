import json
from pathlib import Path

CONFIG=Path("data/job_sources.json")

def test_talentreef_sources_are_always_client_scoped():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"))
    for provider in ("talentreef","jobappnetwork"):
        for src in cfg.get(provider,[]):
            assert src.get("client_id") or src.get("clientId"), (
                f"{provider} source {src.get('company')} is unsafe/unusable without client_id"
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
