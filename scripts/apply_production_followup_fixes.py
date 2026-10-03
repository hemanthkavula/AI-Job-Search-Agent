from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        if new in text:
            print(f"already patched: {path}")
            return
        raise RuntimeError(f"expected block not found in {path}: {old[:120]!r}")
    if count != 1:
        raise RuntimeError(f"expected exactly one match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched: {path}")


# 1) Unhealthy-source retry TTL. Health probes remain advisory; a source that is
# still marked unhealthy gets a real adapter retry every 6 hours instead of being
# suppressed forever by a health file that is refreshed every production cycle.
replace_once(
    "app/discovery.py",
    "from datetime import datetime, timezone\n",
    "from datetime import datetime, timezone, timedelta\n",
)

replace_once(
    "app/discovery.py",
    'def discover(config: dict, only_source=None, dice_search_terms=None, registry_path=None, hours=24, health_path="state/source_health.json", source_hours=None, source_unit_hours=None, return_coverage=False) -> list[dict]:\n',
    'def discover(config: dict, only_source=None, dice_search_terms=None, registry_path=None, hours=24, health_path="state/source_health.json", source_retry_path="state/source_retry_state.json", unhealthy_retry_hours=6, source_hours=None, source_unit_hours=None, return_coverage=False) -> list[dict]:\n',
)

replace_once(
    "app/discovery.py",
    '''    unhealthy_career_sites=set()\n    unhealthy_units=set()\n    try:\n        from pathlib import Path\n        import time\n        health_file=Path(health_path)\n''',
    '''    unhealthy_career_sites=set()\n    unhealthy_units=set()\n    unhealthy_status={}\n    retry_state={}\n    retry_now=datetime.now(timezone.utc)\n    try:\n        from pathlib import Path\n        import time\n        retry_file=Path(source_retry_path)\n        try:\n            retry_state=json.loads(retry_file.read_text(encoding="utf-8")) if retry_file.exists() else {}\n        except Exception:\n            retry_state={}\n        health_file=Path(health_path)\n''',
)

replace_once(
    "app/discovery.py",
    '''                if status in {"no_crawlable_links","blocked_or_http_error","unreachable","broken","invalid_pattern"} and row.get("provider") and row.get("company"):\n                    unhealthy_units.add((row["provider"],row["company"]))\n    except Exception:\n        pass\n    # Quarantine stale/broken learned ATS tenants for the health TTL instead of\n''',
    '''                if status in {"no_crawlable_links","blocked_or_http_error","unreachable","broken","invalid_pattern"} and row.get("provider") and row.get("company"):\n                    unit=(row["provider"],row["company"])\n                    unhealthy_units.add(unit)\n                    unhealthy_status[unit]=status\n    except Exception:\n        pass\n\n    def _should_skip_unhealthy(provider, company):\n        """Skip a known-unhealthy unit only until its real-adapter retry TTL expires."""\n        unit=(provider,company)\n        if unit not in unhealthy_units:\n            return False\n        key=f"{provider}:{company or provider}"\n        # An explicit provider-only diagnostic is a manual retry and must never be\n        # defeated by the cached health quarantine.\n        force_retry=only_source==provider\n        previous=retry_state.get(key,{}) if isinstance(retry_state,dict) else {}\n        last_retry=None\n        if isinstance(previous,dict):\n            value=previous.get("last_retry_at")\n            if value:\n                try:\n                    last_retry=datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(timezone.utc)\n                except Exception:\n                    last_retry=None\n        retry_due=force_retry or last_retry is None or (retry_now-last_retry)>=timedelta(hours=max(1,float(unhealthy_retry_hours)))\n        if retry_due:\n            retry_state[key]={\n                "source":provider,\n                "company":company,\n                "health_status":unhealthy_status.get(unit),\n                "last_retry_at":retry_now.isoformat(),\n            }\n            return False\n        return True\n\n    # Quarantine stale/broken learned ATS tenants between bounded adapter retries\n''',
)

replace_once(
    "app/discovery.py",
    '''            if (provider,company) in unhealthy_units:\n                health[f"{provider}:{company or provider}"]={"source":provider,"company":company,"status":"SKIPPED_UNHEALTHY","jobs_returned":0,"checked_at":datetime.now(timezone.utc).isoformat()}\n            else:\n                kept.append(src)\n''',
    '''            if _should_skip_unhealthy(provider,company):\n                health[f"{provider}:{company or provider}"]={"source":provider,"company":company,"status":"SKIPPED_UNHEALTHY","jobs_returned":0,"checked_at":datetime.now(timezone.utc).isoformat(),"retry_ttl_hours":unhealthy_retry_hours}\n            else:\n                kept.append(src)\n''',
)

replace_once(
    "app/discovery.py",
    '''            if company in unhealthy_career_sites:\n                key=f"career_site:{company}"\n                health[key]={"source":"career_site","company":company,"status":"SKIPPED_UNHEALTHY","jobs_returned":0,"checked_at":datetime.now(timezone.utc).isoformat()}\n                continue\n''',
    '''            if company in unhealthy_career_sites and _should_skip_unhealthy("career_site",company):\n                key=f"career_site:{company}"\n                health[key]={"source":"career_site","company":company,"status":"SKIPPED_UNHEALTHY","jobs_returned":0,"checked_at":datetime.now(timezone.utc).isoformat(),"retry_ttl_hours":unhealthy_retry_hours}\n                continue\n''',
)

replace_once(
    "app/discovery.py",
    '''    hp.write_text(json.dumps(prior,indent=2),encoding="utf-8")\n    return (rows, errors, coverage) if return_coverage else (rows, errors)\n''',
    '''    hp.write_text(json.dumps(prior,indent=2),encoding="utf-8")\n    rp=__import__("pathlib").Path(source_retry_path);rp.parent.mkdir(parents=True,exist_ok=True)\n    rp.write_text(json.dumps(retry_state,indent=2),encoding="utf-8")\n    return (rows, errors, coverage) if return_coverage else (rows, errors)\n''',
)


# 2) Accurate hard-filter reason aggregation. Keep old summary keys for backward
# compatibility, but stop hiding normal title/location/employment restrictions in
# other_hard_filter.
replace_once(
    "app/daily_runner.py",
    '''def _reason_key(reason):\n    r=(reason or "").lower()\n    if "title outside" in r:return "wrong_job_family"\n    if "experience requirement" in r:return "experience_mismatch"\n    if "sponsorship unavailable" in r:return "no_future_sponsorship"\n    return "other_hard_filter"\n''',
    '''def _reason_key(reason):\n    r=(reason or "").lower()\n    if "data-engineering job family" in r or "title/jd outside" in r:return "wrong_job_family"\n    if "location outside united states" in r:return "location_outside_us"\n    if "employment type outside" in r:return "employment_type_mismatch"\n    if "experience requirement" in r:return "experience_mismatch"\n    if "sponsorship unavailable" in r:return "no_future_sponsorship"\n    if "citizenship required" in r:return "citizenship_restriction"\n    if "clearance required" in r:return "clearance_restriction"\n    if "excluded prior employer" in r:return "excluded_prior_employer"\n    return "other_hard_filter"\n''',
)

replace_once(
    "app/daily_runner.py",
    '''    diagnostics={\n        "fresh_jobs_checked":len(jobs24),"target_company_jobs":target_fresh,"target_company_eligible":target_eligible,"target_company_rejected":target_rejected,"wrong_job_family":reason_counts["wrong_job_family"],\n        "experience_mismatch":reason_counts["experience_mismatch"],"no_future_sponsorship":reason_counts["no_future_sponsorship"],\n        "duplicates_removed":len(duplicates),"outside_target_company":reason_counts["outside_target_company"],\n        "other_hard_filter":reason_counts["other_hard_filter"],"already_processed_ledger":reason_counts["already_processed_ledger"],"eligible_for_resume":len(eligible),\n    }\n''',
    '''    diagnostics={\n        "fresh_jobs_checked":len(jobs24),"target_company_jobs":target_fresh,"target_company_eligible":target_eligible,"target_company_rejected":target_rejected,"wrong_job_family":reason_counts["wrong_job_family"],\n        "location_outside_us":reason_counts["location_outside_us"],"employment_type_mismatch":reason_counts["employment_type_mismatch"],\n        "experience_mismatch":reason_counts["experience_mismatch"],"no_future_sponsorship":reason_counts["no_future_sponsorship"],\n        "citizenship_restriction":reason_counts["citizenship_restriction"],"clearance_restriction":reason_counts["clearance_restriction"],\n        "excluded_prior_employer":reason_counts["excluded_prior_employer"],\n        "duplicates_removed":len(duplicates),"outside_target_company":reason_counts["outside_target_company"],\n        "other_hard_filter":reason_counts["other_hard_filter"],"already_processed_ledger":reason_counts["already_processed_ledger"],"eligible_for_resume":len(eligible),\n    }\n''',
)

replace_once(
    "app/daily_runner.py",
    '''    labels=[("Fresh verified jobs","fresh_jobs_checked"),("Wrong job family","wrong_job_family"),("Experience mismatch","experience_mismatch"),("No future sponsorship","no_future_sponsorship"),("Duplicates removed","duplicates_removed"),("Other eligibility filter","other_hard_filter"),("Already processed ledger","already_processed_ledger"),("Eligible for resume","eligible_for_resume")]\n''',
    '''    labels=[("Fresh verified jobs","fresh_jobs_checked"),("Wrong job family","wrong_job_family"),("Location outside US","location_outside_us"),("Employment type mismatch","employment_type_mismatch"),("Experience mismatch","experience_mismatch"),("No future sponsorship","no_future_sponsorship"),("Citizenship restriction","citizenship_restriction"),("Clearance restriction","clearance_restriction"),("Excluded prior employer","excluded_prior_employer"),("Duplicates removed","duplicates_removed"),("Other eligibility filter","other_hard_filter"),("Already processed ledger","already_processed_ledger"),("Eligible for resume","eligible_for_resume")]\n''',
)


# 3) updated_at is only provisional freshness evidence. A direct ATS job admitted
# through updated_at_fallback must prove its actual employer/ATS posting date during
# finalization, exactly as an aggregator-origin lead already must.
replace_once(
    "app/jd_finalizer.py",
    '''        official_posted=None;official_label=None\n        if aggregator_origin:\n            # Aggregator timestamps are discovery evidence only. Re-read the\n            # resolved employer/ATS page and enforce its authoritative date.\n            official_page=_fetch_public_page(application_url)\n            official_posted,official_label=_official_posted_at(official_page,now=check_now)\n        else:\n            # Direct ATS jobs can gain a more authoritative posting field during\n            # detail resolution after the earlier freshness pass. Re-check that\n            # final value here so e.g. Workday "Posted 4 Days Ago" cannot bypass\n            # a ~61-hour production window. If no posting field was added, retain\n            # the result of the earlier strict freshness gate.\n            from app.freshness import _parse_posting_value\n            for field in posting_fields:\n                value=raw.get(field)\n                if value in (None,""):continue\n                official_posted=_parse_posting_value(value,check_now)\n                if official_posted is not None:\n                    official_label=str(value);break\n''',
    '''        official_posted=None;official_label=None\n        provisional_updated_at=raw.get("freshness_basis")=="updated_at_fallback"\n        requires_official_post_date=aggregator_origin or provisional_updated_at\n        if requires_official_post_date:\n            # Aggregator timestamps and generic ATS updated_at values are discovery\n            # evidence only. Re-read the employer/ATS page and require a true\n            # publication date before the job can become Ready-to-Apply.\n            official_page=_fetch_public_page(application_url)\n            official_posted,official_label=_official_posted_at(official_page,now=check_now)\n        else:\n            # Direct ATS jobs can gain a more authoritative posting field during\n            # detail resolution after the earlier freshness pass. Re-check that\n            # final value here so e.g. Workday "Posted 4 Days Ago" cannot bypass\n            # a ~61-hour production window.\n            from app.freshness import _parse_posting_value\n            for field in posting_fields:\n                value=raw.get(field)\n                if value in (None,""):continue\n                official_posted=_parse_posting_value(value,check_now)\n                if official_posted is not None:\n                    official_label=str(value);break\n''',
)

replace_once(
    "app/jd_finalizer.py",
    '''        if aggregator_origin and official_posted is None:\n            held.append({"job":raw,"action":"HOLD_OFFICIAL_POST_DATE_UNVERIFIED","reason":"Official employer/ATS posting date could not be verified at finalization. Aggregator/repost dates are discovery evidence only and are never used as freshness authority.","diagnostics":{"url":application_url,"discovery_source":raw.get("source"),"ats_resolution":raw.get("ats_resolution")}})\n            continue\n''',
    '''        if requires_official_post_date and official_posted is None:\n            reason=("Official employer/ATS posting date could not be verified at finalization. Aggregator/repost dates are discovery evidence only and are never used as freshness authority." if aggregator_origin else "The ATS updated_at timestamp is only a modification timestamp and cannot prove when the job was posted. An authoritative employer/ATS posting date could not be verified at finalization.")\n            held.append({"job":raw,"action":"HOLD_OFFICIAL_POST_DATE_UNVERIFIED","reason":reason,"diagnostics":{"url":application_url,"discovery_source":raw.get("source"),"ats_resolution":raw.get("ats_resolution"),"discovery_freshness_basis":raw.get("freshness_basis")}})\n            continue\n''',
)


# Regression tests.
Path("tests/test_rejection_reason_reporting.py").write_text('''from app.daily_runner import _reason_key\n\n\ndef test_reason_keys_are_reported_in_specific_buckets():\n    cases={\n        "title/JD outside data-engineering job family":"wrong_job_family",\n        "location outside United States target":"location_outside_us",\n        "employment type outside Full-Time/W-2 target":"employment_type_mismatch",\n        "experience requirement not met: 10 years required":"experience_mismatch",\n        "future H-1B sponsorship unavailable":"no_future_sponsorship",\n        "US citizenship required":"citizenship_restriction",\n        "security/public-trust clearance required":"clearance_restriction",\n        "excluded prior employer":"excluded_prior_employer",\n    }\n    for reason,expected in cases.items():\n        assert _reason_key(reason)==expected\n\n\ndef test_unknown_reason_remains_other_hard_filter():\n    assert _reason_key("some new future restriction")=="other_hard_filter"\n''', encoding="utf-8")

Path("tests/test_source_unhealthy_retry.py").write_text('''import json\nfrom datetime import datetime, timezone, timedelta\n\nimport app.discovery as discovery\n\n\ndef _quiet_discovery_dependencies(monkeypatch):\n    monkeypatch.setattr(discovery,"load_registry",lambda *_:{})\n    monkeypatch.setattr(discovery,"as_discovery_config",lambda *_:{})\n    monkeypatch.setattr(discovery,"annotate_jobs",lambda rows:rows)\n    monkeypatch.setattr(discovery,"learn_from_jobs",lambda *args:[])\n    monkeypatch.setattr(discovery,"load_company_registry",lambda :{})\n    monkeypatch.setattr(discovery,"learn_companies_from_jobs",lambda *args:[])\n    monkeypatch.setattr(discovery,"save_company_registry",lambda *args:None)\n\n\ndef test_unhealthy_source_is_skipped_until_retry_ttl_then_retried(tmp_path, monkeypatch):\n    _quiet_discovery_dependencies(monkeypatch)\n    health_path=tmp_path/"source_health.json"\n    retry_path=tmp_path/"source_retry_state.json"\n    health_path.write_text(json.dumps({\n        "sources":[{\n            "provider":"greenhouse",\n            "company":"Acme",\n            "status":"blocked_or_http_error",\n        }]\n    }),encoding="utf-8")\n\n    calls=[]\n    monkeypatch.setattr(discovery,"greenhouse_jobs",lambda token:calls.append(token) or [])\n    config={"greenhouse":[{"company":"Acme","board_token":"acme"}]}\n    now=datetime.now(timezone.utc)\n    retry_path.write_text(json.dumps({\n        "greenhouse:Acme":{\n            "source":"greenhouse",\n            "company":"Acme",\n            "last_retry_at":now.isoformat(),\n        }\n    }),encoding="utf-8")\n\n    _,_,coverage=discovery.discover(\n        config,registry_path=str(tmp_path/"registry.json"),\n        health_path=str(health_path),source_retry_path=str(retry_path),\n        unhealthy_retry_hours=6,return_coverage=True,\n    )\n    assert calls==[]\n    assert coverage["skipped_unhealthy_units"]==1\n\n    retry_path.write_text(json.dumps({\n        "greenhouse:Acme":{\n            "source":"greenhouse",\n            "company":"Acme",\n            "last_retry_at":(now-timedelta(hours=7)).isoformat(),\n        }\n    }),encoding="utf-8")\n    discovery.discover(\n        config,registry_path=str(tmp_path/"registry.json"),\n        health_path=str(health_path),source_retry_path=str(retry_path),\n        unhealthy_retry_hours=6,return_coverage=True,\n    )\n    assert calls==["acme"]\n\n\ndef test_manual_provider_check_forces_retry_even_inside_ttl(tmp_path, monkeypatch):\n    _quiet_discovery_dependencies(monkeypatch)\n    health_path=tmp_path/"source_health.json"\n    retry_path=tmp_path/"source_retry_state.json"\n    health_path.write_text(json.dumps({\n        "sources":[{"provider":"greenhouse","company":"Acme","status":"broken"}]\n    }),encoding="utf-8")\n    retry_path.write_text(json.dumps({\n        "greenhouse:Acme":{"last_retry_at":datetime.now(timezone.utc).isoformat()}\n    }),encoding="utf-8")\n    calls=[]\n    monkeypatch.setattr(discovery,"greenhouse_jobs",lambda token:calls.append(token) or [])\n    discovery.discover(\n        {"greenhouse":[{"company":"Acme","board_token":"acme"}]},\n        only_source="greenhouse",registry_path=str(tmp_path/"registry.json"),\n        health_path=str(health_path),source_retry_path=str(retry_path),\n        unhealthy_retry_hours=6,\n    )\n    assert calls==["acme"]\n''', encoding="utf-8")

Path("tests/test_updated_at_fallback_finalizer.py").write_text('''import json\nfrom datetime import datetime, timezone\n\nimport app.jd_finalizer as finalizer\n\n\ndef _report(tmp_path):\n    url="https://boards.greenhouse.io/acme/jobs/123"\n    report={\n        "results":[{\n            "action":"ELIGIBLE_FOR_RESUME",\n            "job":{\n                "external_id":"greenhouse:acme:123",\n                "source":"greenhouse",\n                "company_key":"Acme",\n                "title":"Senior Data Engineer",\n                "location":"Remote - US",\n                "url":url,\n                "original_url":url,\n                "ats_provider":"greenhouse",\n                "freshness_basis":"updated_at_fallback",\n                "updated_at":"2026-10-03T12:30:00+00:00",\n                "description":"data pipelines etl spark warehouse requirements responsibilities",\n                "description_usable":True,\n            },\n        }]\n    }\n    path=tmp_path/"eligible.json"\n    path.write_text(json.dumps(report),encoding="utf-8")\n    return path\n\n\ndef _patch_common(monkeypatch):\n    monkeypatch.setattr(finalizer,"load_profile",lambda :{})\n    monkeypatch.setattr(finalizer,"resolve_full_jd",lambda job:dict(job))\n\n\ndef test_updated_at_fallback_requires_official_post_date_and_rejects_stale(tmp_path, monkeypatch):\n    _patch_common(monkeypatch)\n    monkeypatch.setattr(finalizer,"_fetch_public_page",lambda url:'<html><script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-10-01T12:00:00Z"}</script></html>')\n    result=finalizer.finalize_report(\n        _report(tmp_path),output_path=tmp_path/"final.json",hours=24,\n        now=datetime(2026,10,3,13,0,tzinfo=timezone.utc),\n    )\n    assert result["finalized"]==0\n    assert result["rejections"][0]["action"]=="REJECT_STALE_OFFICIAL_POSTING"\n\n\ndef test_updated_at_fallback_holds_when_official_post_date_cannot_be_verified(tmp_path, monkeypatch):\n    _patch_common(monkeypatch)\n    monkeypatch.setattr(finalizer,"_fetch_public_page",lambda url:"<html><body>Careers</body></html>")\n    result=finalizer.finalize_report(\n        _report(tmp_path),output_path=tmp_path/"final.json",hours=24,\n        now=datetime(2026,10,3,13,0,tzinfo=timezone.utc),\n    )\n    assert result["finalized"]==0\n    assert result["rejections"][0]["action"]=="HOLD_OFFICIAL_POST_DATE_UNVERIFIED"\n    assert "modification timestamp" in result["rejections"][0]["reason"]\n''', encoding="utf-8")

print("Production follow-up fixes applied.")
