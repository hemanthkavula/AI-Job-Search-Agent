from __future__ import annotations
import argparse, json, re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from app.sources.career_site import validate_source as validate_career_site
from app.discovery import DIRECT_PROVIDERS, FALLBACK_ATS_PROVIDERS, NATIVE_ATS_PROVIDERS, GENERIC_PUBLIC_ATS_PROVIDERS
from app.source_registry import load_registry, as_discovery_config

ROOT=Path(__file__).resolve().parents[1]
UA={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/html,*/*"}

def _probe(url: str, timeout: int=12, method: str="GET", data: bytes|None=None, headers: dict|None=None) -> dict:
    h=dict(UA); h.update(headers or {})
    try:
        with urlopen(Request(url,data=data,headers=h,method=method),timeout=timeout) as resp:
            return {"status":"ok","http_status":getattr(resp,"status",None)}
    except HTTPError as exc:
        return {"status":"broken" if exc.code in (404,410) else "blocked_or_http_error","http_status":exc.code,"error":str(exc)}
    except (URLError,TimeoutError,OSError) as exc:
        return {"status":"unreachable","http_status":None,"error":str(exc)}

def _row(provider, company, target, result, **extra):
    return {"provider":provider,"company":company,"target":target,**result,**extra}

def run(path: str="data/job_sources.json", timeout: int=12) -> dict:
    cfg=json.loads((ROOT/path).read_text(encoding="utf-8"))
    learned=as_discovery_config(load_registry())
    for provider, units in learned.items():
        if not isinstance(units,list):
            continue
        existing=cfg.get(provider)
        if not isinstance(existing,list):
            existing=[]
        seen={json.dumps(x,sort_keys=True,default=str) for x in existing if isinstance(x,dict)}
        for unit in units:
            key=json.dumps(unit,sort_keys=True,default=str)
            if key not in seen:
                existing.append(unit);seen.add(key)
        cfg[provider]=existing
    rows=[]
    career_units=list(cfg.get("career_site",[]))
    def _validate_career(x):
        r=validate_career_site(x["company"],x["search_url"],x["job_url_pattern"],timeout)
        effective=r["status"]
        if effective=="ok" and r.get("matching_job_links",0)==0: effective="no_crawlable_links"
        r["effective_status"]=effective
        return _row("career_site",x["company"],x["search_url"],r)
    if career_units:
        with ThreadPoolExecutor(max_workers=min(16,len(career_units))) as pool:
            rows.extend(pool.map(_validate_career,career_units))
    for x in cfg.get("greenhouse",[]):
        url=f'https://boards-api.greenhouse.io/v1/boards/{x["board_token"]}/jobs'
        rows.append(_row("greenhouse",x.get("company") or x["board_token"],url,_probe(url,timeout)))
    for x in cfg.get("lever",[]):
        url=f'https://api.lever.co/v0/postings/{x["site"]}?mode=json&limit=1'
        rows.append(_row("lever",x.get("company") or x["site"],url,_probe(url,timeout)))
    for x in cfg.get("ashby",[]):
        board_name=quote(str(x["board_name"]).strip(),safe="")
        url=f'https://api.ashbyhq.com/posting-api/job-board/{board_name}'
        rows.append(_row("ashby",x.get("company") or x["board_name"],url,_probe(url,timeout)))
    for x in cfg.get("smartrecruiters",[]):
        ident=x.get("company_identifier") or x.get("identifier")
        url=f'https://api.smartrecruiters.com/v1/companies/{ident}/postings?limit=1&offset=0'
        rows.append(_row("smartrecruiters",x.get("company") or ident,url,_probe(url,timeout)))
    for x in cfg.get("workday",[]):
        url=f'https://{x["host"].strip("/")}/wday/cxs/{x["tenant"]}/{x["site"]}/jobs'
        body=json.dumps({"appliedFacets":{},"limit":1,"offset":0,"searchText":"Data Engineer"}).encode()
        rows.append(_row("workday",x.get("company") or x["tenant"],url,_probe(url,timeout,method="POST",data=body,headers={"Content-Type":"application/json"})))
    for provider in ("successfactors","icims","oracle"):
        for x in cfg.get(provider,[]):
            url=x.get("base_url") or x.get("search_url") or x.get("careers_url") or x.get("original_url")
            if not url:
                rows.append(_row(provider,x.get("company") or provider,"",{"status":"configured","http_status":None},coverage_status="CONFIGURED"));continue
            rows.append(_row(provider,x.get("company") or provider,url,_probe(url,timeout)))
    for x in cfg.get("eightfold",[]):
        url=x.get("careers_url") or x.get("search_url") or x.get("base_url") or x.get("original_url")
        if not url:
            rows.append(_row("eightfold",x.get("company") or "eightfold","",{"status":"configured","http_status":None},coverage_status="CONFIGURED"));continue
        rows.append(_row("eightfold",x.get("company") or "eightfold",url,_probe(url,timeout)))
    for provider in ("ukg","ultipro","ultipro_ukg","adp_workforce_now","avature","phenom","paylocity","workable","jazzhr","jazzhr_alt","dayforce","cornerstone","jobvite"):
        for x in cfg.get(provider,[]):
            url=x.get("search_url") or x.get("base_url") or x.get("careers_url") or x.get("original_url")
            if not url:
                rows.append(_row(provider,x.get("company") or provider,"",{"status":"configured","http_status":None},coverage_status="CONFIGURED"));continue
            probe=_probe(url,timeout);coverage="DIRECT" if probe.get("status")=="ok" else "BLOCKED"
            rows.append(_row(provider,x.get("company") or provider,url,probe,coverage_status=coverage))
    dedicated={"career_site","greenhouse","lever","ashby","smartrecruiters","workday","successfactors","icims","oracle","eightfold","ukg","ultipro","ultipro_ukg","adp_workforce_now","avature","phenom","paylocity","workable","jazzhr","jazzhr_alt","dayforce","cornerstone","jobvite","dice","ziprecruiter"}
    for provider, units in cfg.items():
        if provider in dedicated or not isinstance(units,list):continue
        for x in units:
            if not isinstance(x,dict):continue
            url=x.get("search_url") or x.get("base_url") or x.get("careers_url") or x.get("original_url")
            if not url:
                rows.append(_row(provider,x.get("company") or provider,"",{"status":"configured","http_status":None},coverage_status="CONFIGURED"));continue
            probe=_probe(url,timeout)
            coverage=("DIRECT_PUBLIC_BOARD" if provider in DIRECT_PROVIDERS else "GENERIC_PUBLIC_REACHABLE") if probe.get("status")=="ok" else "BLOCKED"
            rows.append(_row(provider,x.get("company") or provider,url,probe,coverage_status=coverage,collector_class=("direct_public_board" if provider in DIRECT_PROVIDERS else "generic_public_html")))
    for provider in DIRECT_PROVIDERS:
        units=cfg.get(provider,[])
        if isinstance(units,list) and not units:
            collector_class="native_client_scoped" if provider in {"talentreef","jobappnetwork"} else "unseeded"
            rows.append(_row(provider,provider,"",{"status":"unseeded","http_status":None},coverage_status="UNSEEDED",collector_class=collector_class))

    # IMPORTANT: health probing is advisory. A failed health probe must not become
    # a 24-hour production exclusion. discovery.py historically suppresses rows
    # whose effective_status is broken/unreachable/blocked/etc.; map those observations
    # to probe_required while preserving the raw status for diagnostics. This makes
    # every configured tenant eligible for a recovery attempt on every production run.
    suppressing_statuses={"no_crawlable_links","blocked_or_http_error","unreachable","broken","invalid_pattern","ERROR","SKIPPED_UNHEALTHY"}
    for r in rows:
        observed=r.get("effective_status") or r.get("status")
        r["observed_status"]=observed
        if observed in suppressing_statuses:
            r["effective_status"]="probe_required"
            r["recovery_probe_required"]=True

    counts={}
    for r in rows:
        s=r.get("effective_status") or r["status"];counts[s]=counts.get(s,0)+1
    coverage_counts={}
    for r in rows:
        k=r.get("coverage_status") or ("DIRECT" if (r.get("effective_status") or r.get("status"))=="ok" else "UNKNOWN");coverage_counts[k]=coverage_counts.get(k,0)+1
    return {"counts":counts,"coverage_counts":coverage_counts,"provider_classes":{"native":list(NATIVE_ATS_PROVIDERS),"generic_public":list(GENERIC_PUBLIC_ATS_PROVIDERS),"direct":list(DIRECT_PROVIDERS),"fallback":list(FALLBACK_ATS_PROVIDERS)},"sources":rows}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--sources",default="data/job_sources.json");p.add_argument("--timeout",type=int,default=12);p.add_argument("--output",default="state/source_health.json");a=p.parse_args()
    report=run(a.sources,a.timeout);out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report["counts"],indent=2))
    for r in report["sources"]:
        status=r.get("effective_status") or r["status"]
        if status!="ok":print(f'{status:22} [{r["provider"]}] {r["company"]}: {r["target"]} http={r.get("http_status")} links={r.get("matching_job_links","")} observed={r.get("observed_status","")}')
    print(f"Saved report to {out}")
