from __future__ import annotations
import json
from collections import Counter
from app.company_registry import load

def report(path=None):
    reg=load() if path is None else load(path)
    rows=list(reg.values())
    by_feeder=Counter((r.get("discovered_by") or "unknown") for r in rows)
    by_ats=Counter((r.get("ats_provider") or "unresolved") for r in rows)
    total=len(rows)
    domains=sum(bool(r.get("official_domain")) for r in rows)
    careers=sum(bool(r.get("careers_url")) for r in rows)
    executable=sum(bool(r.get("ats_provider")) for r in rows)
    return {
        "employers_loaded":total,
        "official_domains_resolved":domains,
        "career_pages_resolved":careers,
        "executable_sources":executable,
        "domain_resolution_rate":round(domains/total*100,2) if total else 0,
        "career_resolution_rate":round(careers/total*100,2) if total else 0,
        "executable_source_rate":round(executable/total*100,2) if total else 0,
        "by_feeder":dict(by_feeder.most_common()),
        "by_ats":dict(by_ats.most_common()),
    }

if __name__=="__main__":
    print(json.dumps(report(),indent=2))
