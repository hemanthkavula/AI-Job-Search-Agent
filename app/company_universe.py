from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlparse
from app.company_registry import load as load_registry, save as save_registry, upsert
from app.company_feeders import collect as collect_company_feeders
from app.company_domain_resolver import resolve_company

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
    # Add identity-level companies from authoritative/public universe feeders.
    # These companies still require official-domain/career-page resolution before
    # they become executable job sources.
    feeder_rows,feeder_errors=collect_company_feeders()
    for row in feeder_rows:
        upsert(reg,row.get("company"),discovered_by=row.get("discovered_by"))
        key=(row.get("company") or "").strip().lower()
        if key in reg:
            if row.get("cik"):reg[key]["sec_cik"]=row["cik"]
            if row.get("ticker"):reg[key]["ticker"]=row["ticker"]
    resolved_domains=0
    # Resolve only evidence-backed domains. Never derive domains by company-name guessing.
    for row in reg.values():
        if row.get("official_domain"):continue
        try:
            resolved=resolve_company(row)
            if resolved:
                row.update({k:v for k,v in resolved.items() if v})
                resolved_domains+=1
        except Exception:
            continue
    save_registry(reg,registry_path)
    return {"companies":len(reg),"added":len(reg)-before,"feeder_rows":len(feeder_rows),
            "resolved_domains":resolved_domains,"feeder_errors":feeder_errors}

if __name__=="__main__":
    print(json.dumps(build(),indent=2))
