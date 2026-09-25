from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlparse
from app.company_registry import load as load_registry, save as save_registry, upsert

ROOT=Path(__file__).resolve().parents[1]

def _domain(url):
    try:
        host=urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:return None

def build(source_path="data/job_sources.json", registry_path="generated/company_registry.json"):
    """Seed the open-ended employer universe from every configured company source.

    This is intentionally not an allowlist. Broad discovery and future resolvers
    can add companies that do not appear in job_sources.json.
    """
    cfg=json.loads((ROOT/source_path).read_text(encoding="utf-8"))
    reg=load_registry(registry_path)
    before=len(reg)
    for provider,units in cfg.items():
        if not isinstance(units,list):continue
        for row in units:
            if not isinstance(row,dict):continue
            company=row.get("company")
            if not company:continue
            url=row.get("careers_url") or row.get("search_url") or row.get("base_url")
            # ATS URLs are useful as known career sources, but are not assumed to
            # be the employer's corporate domain.
            upsert(reg,company,careers_url=url,ats_provider=None if provider=="career_site" else provider,
                   discovered_by="configured_source")
    save_registry(reg,registry_path)
    return {"companies":len(reg),"added":len(reg)-before}

if __name__=="__main__":
    print(json.dumps(build(),indent=2))
