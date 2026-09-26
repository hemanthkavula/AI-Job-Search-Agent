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
from app.sources.successfactors import fetch_jobs as successfactors_jobs
from app.sources.icims import fetch_jobs as icims_jobs
from app.sources.oracle import fetch_jobs as oracle_jobs
from app.sources.career_site import fetch_jobs as career_site_jobs
from app.sources.eightfold import fetch_jobs as eightfold_jobs
from app.sources.ukg import fetch_jobs as ukg_jobs
from app.sources.adp_workforce_now import fetch_jobs as adp_jobs
from app.sources.avature import fetch_jobs as avature_jobs
from app.sources.phenom import fetch_jobs as phenom_jobs
from app.sources.paylocity import fetch_jobs as paylocity_jobs
from app.sources.workable import fetch_jobs as workable_jobs
from app.sources.jazzhr import fetch_jobs as jazzhr_jobs
from app.sources.dayforce import fetch_jobs as dayforce_jobs
from app.sources.cornerstone import fetch_jobs as cornerstone_jobs
from app.sources.jobvite import fetch_jobs as jobvite_jobs
from app.sources.public_ats_board import fetch_jobs as public_ats_jobs
from app.sources.talentreef import fetch_jobs as talentreef_jobs
from app.source_registry import load_registry, save_registry, learn_from_jobs, as_discovery_config, DEFAULT_PATH
from app.ats_resolver import resolve_original_ats
from app.target_companies import annotate_jobs
import json

DIRECT_PROVIDERS=("greenhouse","lever","ashby","smartrecruiters","workday","successfactors","icims","oracle","eightfold","ukg","ultipro","ultipro_ukg","adp_workforce_now","avature","phenom","paylocity","workable","jazzhr","jazzhr_alt","dayforce","cornerstone","jobvite","recruitee","teamtailor","bamboohr","breezyhr","rippling","pinpoint","careerplug","freshteam","jobscore","personio","comeet","neogov","clearcompany","applicantpro","fountain","hirebridge","zoho_recruit","manatal","join","applitrack","hireology","paycor","peopleadmin","isolved","hibob","gohire","hiringthing","homerun","pageup","dover","gem","polymer","hirehive","deel","applicantstack","ceipal","trakstar_hire","recruiting_com","taleo","brassring","paycom","bullhorn","jobdiva","greenhouse_eu","trinet","kula","rival","werecruit","firststage","recruiterbox","talentbrew","radancy","paradox","schooljobs","higheredjobs","applynow","talentreef","icims_alt","jobappnetwork","myworkchoice")
FALLBACK_ATS_PROVIDERS=()
ALL_ATS_PROVIDERS=DIRECT_PROVIDERS+FALLBACK_ATS_PROVIDERS

def discover(config: dict, only_source=None, dice_search_terms=None, registry_path=None, hours=24, health_path="state/source_health.json", source_hours=None, source_unit_hours=None) -> list[dict]:
    registry_path=registry_path or str(DEFAULT_PATH)
    source_hours=source_hours or {}
    source_unit_hours=source_unit_hours or {}
    def _hours(source): return source_hours.get(source,hours)
    def _unit_hours(source, unit): return source_unit_hours.get(f"{source}:{unit}", _hours(source))
    registry=load_registry(registry_path);learned_config=as_discovery_config(registry)
    merged=dict(config)
    for provider in ALL_ATS_PROVIDERS:
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
    # Reuse the latest source-health report to avoid repeatedly crawling generic
    # career pages that are already known to be blocked, unreachable, or JS-only.
    unhealthy_career_sites=set()
    try:
        from pathlib import Path
        import time
        health_file=Path(health_path)
        # Backward-compatible migration: use the old generated report once if
        # state/source_health.json has not been created yet.
        if not health_file.exists() and Path("generated/source_health.json").exists():
            health_file=Path("generated/source_health.json")
        # Health is advisory and expires after 24h. A blocked/JS-only site is
        # skipped during normal hourly scans, then automatically retried after
        # the TTL so temporary outages never become permanent exclusions.
        health_fresh=health_file.exists() and (time.time()-health_file.stat().st_mtime)<=86400
        if health_fresh:
            health_report=json.loads(health_file.read_text(encoding="utf-8"))
            for row in health_report.get("sources",[]):
                status=row.get("effective_status") or row.get("status")
                if row.get("provider")=="career_site" and status in {"no_crawlable_links","blocked_or_http_error","unreachable","broken","invalid_pattern"}:
                    if row.get("company"):
                        unhealthy_career_sites.add(row["company"])
    except Exception:
        pass
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
        for src in config.get("successfactors",[]) if only_source in (None,"successfactors") else []:
            tasks.append((pool.submit(successfactors_jobs,src["company"],src["base_url"]),"successfactors",src.get("company")))
        for src in config.get("icims",[]) if only_source in (None,"icims") else []:
            tasks.append((pool.submit(icims_jobs,src["company"],src["base_url"]),"icims",src.get("company")))
        for src in config.get("oracle",[]) if only_source in (None,"oracle") else []:
            tasks.append((pool.submit(oracle_jobs,src["company"],src["base_url"]),"oracle",src.get("company")))
        for src in config.get("career_site",[]) if only_source in (None,"career_site") else []:
            company=src.get("company")
            if company in unhealthy_career_sites:
                key=f"career_site:{company}"
                health[key]={"source":"career_site","company":company,"status":"SKIPPED_UNHEALTHY","jobs_returned":0,"checked_at":datetime.now(timezone.utc).isoformat()}
                continue
            tasks.append((pool.submit(career_site_jobs,src["company"],src["search_url"],src["job_url_pattern"]),"career_site",company))
        for src in config.get("eightfold",[]) if only_source in (None,"eightfold") else []:
            tasks.append((pool.submit(eightfold_jobs,src["company"],src["careers_url"]),"eightfold",src.get("company")))
        for provider in ("ukg","ultipro","ultipro_ukg"):
            for src in config.get(provider,[]) if only_source in (None,provider) else []:
                url=src.get("search_url") or src.get("base_url") or src.get("careers_url")
                if url:
                    tasks.append((pool.submit(ukg_jobs,src.get("company") or provider,url),provider,src.get("company") or provider))
        for src in config.get("adp_workforce_now",[]) if only_source in (None,"adp_workforce_now") else []:
            url=src.get("search_url") or src.get("base_url") or src.get("careers_url")
            if url:
                tasks.append((pool.submit(adp_jobs,src.get("company") or "adp_workforce_now",url),"adp_workforce_now",src.get("company") or "adp_workforce_now"))
        for src in config.get("avature",[]) if only_source in (None,"avature") else []:
            url=src.get("search_url") or src.get("base_url") or src.get("careers_url")
            if url:
                tasks.append((pool.submit(avature_jobs,src.get("company") or "avature",url),"avature",src.get("company") or "avature"))
        for src in config.get("phenom",[]) if only_source in (None,"phenom") else []:
            url=src.get("search_url") or src.get("base_url") or src.get("careers_url")
            if url:
                tasks.append((pool.submit(phenom_jobs,src.get("company") or "phenom",url),"phenom",src.get("company") or "phenom"))
        for src in config.get("paylocity",[]) if only_source in (None,"paylocity") else []:
            url=src.get("search_url") or src.get("base_url") or src.get("careers_url")
            if url:
                tasks.append((pool.submit(paylocity_jobs,src.get("company") or "paylocity",url),"paylocity",src.get("company") or "paylocity"))
        for src in config.get("workable",[]) if only_source in (None,"workable") else []:
            url=src.get("search_url") or src.get("base_url") or src.get("careers_url")
            if url:tasks.append((pool.submit(workable_jobs,src.get("company") or "workable",url),"workable",src.get("company") or "workable"))
        for provider in ("jazzhr","jazzhr_alt"):
            for src in config.get(provider,[]) if only_source in (None,provider) else []:
                url=src.get("search_url") or src.get("base_url") or src.get("careers_url")
                if url:tasks.append((pool.submit(jazzhr_jobs,src.get("company") or provider,url),provider,src.get("company") or provider))
        for src in config.get("dayforce",[]) if only_source in (None,"dayforce") else []:
            url=src.get("search_url") or src.get("base_url") or src.get("careers_url")
            if url:tasks.append((pool.submit(dayforce_jobs,src.get("company") or "dayforce",url),"dayforce",src.get("company") or "dayforce"))
        for src in config.get("cornerstone",[]) if only_source in (None,"cornerstone") else []:
            url=src.get("search_url") or src.get("base_url") or src.get("careers_url")
            if url:tasks.append((pool.submit(cornerstone_jobs,src.get("company") or "cornerstone",url),"cornerstone",src.get("company") or "cornerstone"))
        for src in config.get("jobvite",[]) if only_source in (None,"jobvite") else []:
            url=src.get("search_url") or src.get("base_url") or src.get("careers_url")
            if url:tasks.append((pool.submit(jobvite_jobs,src.get("company") or "jobvite",url),"jobvite",src.get("company") or "jobvite"))
        # Long-tail ATS families use the hardened generic crawler until a provider-specific adapter exists.
        # Keep these visible as fallback coverage, but do not confuse URL recognition with a working collector.
        # This gives production coverage immediately while preserving provider identity;
        for provider in ("recruitee","teamtailor","bamboohr","breezyhr","rippling","pinpoint","careerplug","freshteam","jobscore","personio","comeet","clearcompany","applicantpro","fountain","hirebridge","zoho_recruit","manatal","join","applitrack","hireology","paycor","peopleadmin","isolved","hibob","gohire","hiringthing","homerun","pageup","dover","gem","polymer","hirehive","deel","applicantstack","ceipal","trakstar_hire","neogov"):
            for src in config.get(provider,[]) if only_source in (None,provider) else []:
                url=src.get("search_url") or src.get("base_url") or src.get("careers_url") or src.get("original_url")
                if not url: continue
                tasks.append((pool.submit(public_ats_jobs,src.get("company") or provider,url,provider,src.get("job_url_pattern",r".+")),provider,src.get("company") or provider))
        # TalentReef and JobAppNetwork share the same applicant-facing platform/API.
        # Require a configured client_id so discovery stays employer-scoped.
        for provider in ("talentreef","jobappnetwork"):
            for src in config.get(provider,[]) if only_source in (None,provider) else []:
                client_id=src.get("client_id") or src.get("clientId") or ""
                search_url=src.get("search_url") or src.get("base_url") or src.get("careers_url") or ""
                if not client_id and not search_url:
                    errors.append({"source":provider,"company":src.get("company"),"error":"Missing client_id or search_url"})
                    continue
                tasks.append((pool.submit(talentreef_jobs,src.get("company") or provider,str(client_id),search_url=search_url),provider,src.get("company") or provider))
        for provider in ("recruiting_com","taleo","brassring","paycom","bullhorn","jobdiva","greenhouse_eu","trinet","kula","rival","werecruit","firststage","recruiterbox","talentbrew","radancy","paradox","schooljobs","higheredjobs","applynow","icims_alt","myworkchoice"):
            for src in config.get(provider,[]) if only_source in (None,provider) else []:
                url=src.get("search_url") or src.get("base_url") or src.get("careers_url") or src.get("original_url")
                if not url: continue
                tasks.append((pool.submit(public_ats_jobs,src.get("company") or provider,url,provider,src.get("job_url_pattern",r".+")),provider,src.get("company") or provider))
        # Reserved fallback path for newly recognized ATS families until promoted.
        for provider in FALLBACK_ATS_PROVIDERS:
            for src in config.get(provider,[]) if only_source in (None,provider) else []:
                url=src.get("search_url")
                if not url:continue
                tasks.append((pool.submit(career_site_jobs,src.get("company") or provider,url,src.get("job_url_pattern",r".+")),provider,src.get("company") or provider))
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
    configured_units={provider:len(config.get(provider,[])) for provider in ALL_ATS_PROVIDERS}
    configured_units["career_site"]=len(config.get("career_site",[]))
    configured_units["dice"]=1 if config.get("dice",{}).get("enabled",False) else 0
    configured_units["ziprecruiter"]=1 if config.get("ziprecruiter",{}).get("enabled",False) else 0
    provider_counts={}
    for row in rows:
        provider_counts[row.get("source")]=provider_counts.get(row.get("source"),0)+1
    for provider in ALL_ATS_PROVIDERS+("career_site","dice","ziprecruiter"):
        if only_source not in (None,provider):
            continue
        relevant=[v for v in health.values() if v.get("source")==provider]
        errors_for_provider=sum(v.get("status")=="ERROR" for v in relevant)
        skipped_for_provider=sum(v.get("status")=="SKIPPED_UNHEALTHY" for v in relevant)
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
            f"jobs_returned={provider_counts.get(provider,0)} | healthy_units={ok_for_provider} | failed_units={errors_for_provider} | skipped_unhealthy={skipped_for_provider}",
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
