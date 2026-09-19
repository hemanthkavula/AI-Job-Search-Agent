from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from app.sources.greenhouse import fetch_jobs as greenhouse_jobs
from app.sources.lever import fetch_jobs as lever_jobs
from app.sources.ashby import fetch_jobs as ashby_jobs
from app.sources.smartrecruiters import fetch_jobs as smartrecruiters_jobs
from app.sources.workday import fetch_jobs as workday_jobs
from app.sources.dice import fetch_jobs as dice_jobs
from app.sources.ziprecruiter import fetch_jobs as ziprecruiter_jobs
from app.source_registry import load_registry, save_registry, learn_from_jobs, as_discovery_config
from app.ats_resolver import resolve_original_ats
from app.target_companies import annotate_jobs
import json

def discover(config: dict, only_source=None, dice_search_terms=None, registry_path="generated/discovered_sources.json", hours=24, health_path="generated/source_health.json", source_hours=None, source_unit_hours=None) -> list[dict]:
    source_hours=source_hours or {}
    source_unit_hours=source_unit_hours or {}
    def _hours(source): return source_hours.get(source,hours)
    def _unit_hours(source, unit): return source_unit_hours.get(f"{source}:{unit}", _hours(source))
    registry=load_registry(registry_path);learned_config=as_discovery_config(registry)
    merged=dict(config)
    for provider in ("greenhouse","lever","ashby","smartrecruiters","workday"):
        existing=list(config.get(provider,[]))
        if provider=="workday":
            seen={(x.get("host"),x.get("tenant"),x.get("site")) for x in existing}
            for row in learned_config.get(provider,[]):
                key=(row.get("host"),row.get("tenant"),row.get("site"))
                if key not in seen:
                    existing.append(row);seen.add(key)
        else:
            seen={str(x) for x in existing}
            for row in learned_config.get(provider,[]):
                if str(row) not in seen:existing.append(row)
        merged[provider]=existing
    config=merged
    jobs=[]
    errors=[]
    tasks=[]
    health={}
    # Network-bound ATS/company calls are independent. Run them concurrently so a
    # slow Workday tenant cannot serially block every other source in the hourly cycle.
    with ThreadPoolExecutor(max_workers=10) as pool:
        for src in config.get("greenhouse",[]) if only_source in (None,"greenhouse") else []:
            tasks.append((pool.submit(greenhouse_jobs,src["board_token"]),"greenhouse",src.get("company")))
        for src in config.get("lever",[]) if only_source in (None,"lever") else []:
            tasks.append((pool.submit(lever_jobs,src["site"]),"lever",src.get("company")))
        for src in config.get("ashby",[]) if only_source in (None,"ashby") else []:
            tasks.append((pool.submit(ashby_jobs,src["board_name"]),"ashby",src.get("company")))
        for src in config.get("smartrecruiters",[]) if only_source in (None,"smartrecruiters") else []:
            identifier=src.get("company_identifier") or src.get("identifier")
            if not identifier:
                errors.append({"source":"smartrecruiters","company":src.get("company"),"error":"Missing company_identifier"})
            else:
                tasks.append((pool.submit(smartrecruiters_jobs,identifier,hours=_hours("smartrecruiters")),"smartrecruiters",src.get("company") or identifier))
        for src in config.get("workday",[]) if only_source in (None,"workday") else []:
            tasks.append((pool.submit(workday_jobs,src.get("company") or src["tenant"],src["host"],src["tenant"],src["site"],src.get("locale","en-US"),hours=_unit_hours("workday",src.get("company") or src.get("tenant"))),"workday",src.get("company") or src.get("tenant")))
        if only_source in (None,"dice") and config.get("dice",{}).get("enabled",False):
            tasks.append((pool.submit(dice_jobs,config.get("dice",{}).get("jobs_per_page",100),search_terms=dice_search_terms,hours=_hours("dice")),"dice","Dice"))
        if only_source in (None,"ziprecruiter") and config.get("ziprecruiter",{}).get("enabled",False):
            tasks.append((pool.submit(ziprecruiter_jobs),"ziprecruiter","ZipRecruiter"))
        for future,source,company in tasks:
            key=f"{source}:{company or source}"
            started=datetime.now(timezone.utc)
            try:
                result=future.result();jobs.extend(result)
                health[key]={"source":source,"company":company,"status":"OK","jobs_returned":len(result),"checked_at":started.isoformat()}
            except Exception as e:
                err={"source":source,"company":company,"error":str(e)};errors.append(err)
                health[key]={"source":source,"company":company,"status":"ERROR","jobs_returned":0,"error":str(e),"checked_at":started.isoformat()}

    dedup={}
    for job in jobs:
        dedup[job["external_id"]]=job
    rows=annotate_jobs(list(dedup.values()))

    # Broad discovery sources often point at an aggregator URL first. Resolve those
    # pages before learning so the employer's real ATS can seed future direct scans.
    learnable=[]
    for row in rows:
        if row.get("source") in {"dice","ziprecruiter"}:
            learnable.append(resolve_original_ats(row))
        else:
            learnable.append(row)

    # Emit a provider-level summary for every supported source so a provider that
    # returned zero jobs is still visible instead of looking as if it never ran.
    configured_units={
        "greenhouse": len(config.get("greenhouse",[])),
        "lever": len(config.get("lever",[])),
        "ashby": len(config.get("ashby",[])),
        "smartrecruiters": len(config.get("smartrecruiters",[])),
        "workday": len(config.get("workday",[])),
        "dice": 1 if config.get("dice",{}).get("enabled",False) else 0,
        "ziprecruiter": 1 if config.get("ziprecruiter",{}).get("enabled",False) else 0,
    }
    provider_counts={}
    for row in rows:
        provider_counts[row.get("source")]=provider_counts.get(row.get("source"),0)+1
    for provider in ("greenhouse","lever","ashby","smartrecruiters","workday","dice","ziprecruiter"):
        if only_source not in (None,provider):
            continue
        relevant=[v for v in health.values() if v.get("source")==provider]
        errors_for_provider=sum(v.get("status")=="ERROR" for v in relevant)
        ok_for_provider=sum(v.get("status")=="OK" for v in relevant)
        if not configured_units.get(provider):
            status="DISABLED"
        elif errors_for_provider and ok_for_provider:
            status="PARTIAL"
        elif errors_for_provider:
            status="ERROR"
        else:
            status="OK"
        print(
            f"SOURCE {provider}: status={status} | configured_units={configured_units.get(provider,0)} | "
            f"jobs_returned={provider_counts.get(provider,0)} | healthy_units={ok_for_provider} | failed_units={errors_for_provider}",
            flush=True,
        )
    learned=learn_from_jobs(learnable,registry)
    if learned:
        for item in learned:
            print(f"LEARNED ATS {item.get('provider')}: {item.get('company')} | {item.get('identifier')}",flush=True)
    if learned:save_registry(registry,registry_path)
    # Persist source health independently from cycle output so the dashboard and
    # scheduler can surface degraded ATS/job-board coverage instead of silently
    # treating a failed provider as "zero jobs".
    hp=__import__("pathlib").Path(health_path);hp.parent.mkdir(parents=True,exist_ok=True)
    try:
        prior=json.loads(hp.read_text(encoding="utf-8")) if hp.exists() else {}
    except Exception:prior={}
    prior.update(health)
    hp.write_text(json.dumps(prior,indent=2),encoding="utf-8")
    return rows, errors
