from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.company_registry import company_key, load as load_company_registry, save as save_company_registry
from app.company_domain_resolver import resolve_company
from app.career_page_resolver import resolve as resolve_career_page
from app.ats_tenant_resolver import resolve as resolve_ats_tenant
from app.source_registry import (
    load_registry as load_source_registry,
    replace_resolved_source,
    save_registry as save_source_registry,
)
from app.source_reliability import STATE_PATH as RETRY_STATE_PATH, _load as load_retry_state, _save as save_retry_state

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = Path(os.getenv("JOB_AGENT_SOURCE_REPAIR_QUEUE", ROOT / "state" / "source_repair_queue.json"))


def _load(path=QUEUE_PATH):
    p = Path(path)
    if not p.exists():
        return {"version": 1, "items": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("items"), dict):
            return data
    except Exception:
        pass
    return {"version": 1, "items": {}}


def _save(data, path=QUEUE_PATH):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def update_from_reliability(retry_state_path=RETRY_STATE_PATH, queue_path=QUEUE_PATH, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    retry = load_retry_state(retry_state_path)
    queue = _load(queue_path)
    items = queue.setdefault("items", {})
    for key, row in (retry.get("units") or {}).items():
        if not row.get("repair_required"):
            continue
        item = items.setdefault(key, {
            "key": key,
            "source": row.get("source"),
            "company": row.get("company"),
            "status": "PENDING",
            "attempts": 0,
            "first_seen_at": now.isoformat(),
        })
        # Do not reopen a repaired source unless it fails again after repair.
        if item.get("status") == "REPAIRED" and row.get("last_success_at") and item.get("repaired_at"):
            try:
                success = datetime.fromisoformat(str(row["last_success_at"]).replace("Z","+00:00"))
                repaired = datetime.fromisoformat(str(item["repaired_at"]).replace("Z","+00:00"))
                if success >= repaired:
                    continue
            except Exception:
                pass
        item.update({
            "source": row.get("source"),
            "company": row.get("company"),
            "failure_class": row.get("failure_class"),
            "last_error": row.get("last_error"),
            "consecutive_failures": row.get("consecutive_failures", 0),
            "last_seen_at": now.isoformat(),
        })
        if item.get("status") in {"FAILED", "REPAIRED"}:
            item["status"] = "PENDING"
    queue["updated_at"] = now.isoformat()
    _save(queue, queue_path)
    return queue


def _due(item, now):
    if item.get("status") not in {"PENDING", "FAILED"}:
        return False
    value = item.get("next_attempt_at")
    if not value:
        return True
    try:
        return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(timezone.utc) <= now
    except Exception:
        return True


def _resolve_replacement(company, company_row):
    # Prefer the verified employer domain when known.
    row = dict(company_row or {})
    row.setdefault("company", company)
    if not row.get("official_domain"):
        domain = resolve_company(row, allow_name_search=True)
        if domain:
            row.update({k:v for k,v in domain.items() if v})
    if row.get("official_domain"):
        hit = resolve_career_page(row["official_domain"])
        if hit:
            return hit, row
    # Domainless employers can still be repaired from a hosted ATS whose board
    # identity matches the employer.
    hit = resolve_ats_tenant(company)
    return hit, row


def repair(limit=25, queue_path=QUEUE_PATH, retry_state_path=RETRY_STATE_PATH, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    queue = update_from_reliability(retry_state_path, queue_path, now)
    company_registry = load_company_registry()
    source_registry = load_source_registry()

    # Fresh job-board leads that could not be mapped to an employer ATS are
    # actionable repair work too. Add them to the same bounded repair queue so
    # the post-production repair step can resolve them immediately.
    items=queue.setdefault("items",{})
    for reg_key,row in company_registry.items():
        if not isinstance(row,dict) or not row.get("ats_resolution_pending"):
            continue
        if row.get("ats_provider") and row.get("careers_url"):
            row["ats_resolution_pending"]=False
            continue
        company=row.get("company") or reg_key
        key=f"resolve:{reg_key}"
        item=items.setdefault(key,{
            "key":key,"source":"unresolved_aggregator","company":company,
            "status":"PENDING","attempts":0,
            "first_seen_at":row.get("ats_resolution_pending_at") or now.isoformat(),
        })
        item.update({
            "company":company,
            "source":"unresolved_aggregator",
            "failure_class":"resolution",
            "last_error":"EMPLOYER_ATS_UNRESOLVED",
            "last_seen_at":row.get("ats_resolution_pending_at") or now.isoformat(),
            "priority":"fresh_job_board_lead",
        })

    pending = sorted(
        (item for item in queue.get("items", {}).values() if _due(item, now)),
        key=lambda x: (
            0 if x.get("priority") == "fresh_job_board_lead" else (1 if x.get("failure_class") == "hard" else 2),
            -int(x.get("consecutive_failures") or 0),
            x.get("first_seen_at") or "",
        ),
    )[:max(0, int(limit))]
    repaired = 0
    failed = 0

    for item in pending:
        company = str(item.get("company") or "").strip()
        provider = str(item.get("source") or "").strip()
        if not company or not provider:
            item["status"] = "FAILED"
            item["last_repair_error"] = "MISSING_COMPANY_OR_PROVIDER"
            failed += 1
            continue
        item["attempts"] = int(item.get("attempts") or 0) + 1
        item["last_attempt_at"] = now.isoformat()
        try:
            company_row = company_registry.get(company_key(company)) or {"company": company}
            hit, enriched_row = _resolve_replacement(company, company_row)
            if not hit or not hit.get("careers_url") or not hit.get("ats_provider"):
                raise RuntimeError("NO_VERIFIED_REPLACEMENT_SOURCE")
            replacement_provider = hit.get("ats_provider")
            replacement_url = hit.get("careers_url")
            replacement_id = hit.get("ats_identifier")
            changed = replace_resolved_source(
                provider,
                replacement_provider,
                company,
                replacement_url,
                source_registry,
                identifier=replacement_id,
                learned_from="automatic_source_repair",
            )
            canonical = company_registry.setdefault(company_key(company), {"company": company})
            canonical.update({k:v for k,v in enriched_row.items() if v})
            canonical.update({
                "careers_url": replacement_url,
                "ats_provider": replacement_provider,
                "ats_identifier": replacement_id,
                "source_repaired_at": now.isoformat(),
                "source_repair_from_provider": provider,
                "ats_resolution_pending": False,
                "ats_resolution_resolved_at": now.isoformat(),
            })
            item.update({
                "status": "REPAIRED",
                "repaired_at": now.isoformat(),
                "replacement_provider": replacement_provider,
                "replacement_url": replacement_url,
                "replacement_identifier": replacement_id,
                "registry_changed": bool(changed),
                "next_attempt_at": None,
                "last_repair_error": None,
            })
            retry_state=load_retry_state(retry_state_path)
            retry_entry=(retry_state.get("units") or {}).get(item.get("key"))
            if retry_entry is not None:
                retry_entry.update({
                    "consecutive_failures":0,
                    "failure_class":None,
                    "repair_required":False,
                    "next_retry_at":now.isoformat(),
                    "last_status":"REPAIRED",
                    "last_error":None,
                    "repaired_at":now.isoformat(),
                })
                save_retry_state(retry_state,retry_state_path)
            repaired += 1
        except Exception as exc:
            item["status"] = "FAILED"
            item["last_repair_error"] = f"{type(exc).__name__}: {exc}"[:500]
            # Failed repair attempts back off independently of normal collector
            # retries; they do not block healthy production sources.
            delay = min(24, 2 ** min(4, int(item.get("attempts") or 1)))
            item["next_attempt_at"] = (now + timedelta(hours=delay)).isoformat()
            failed += 1

    queue["updated_at"] = now.isoformat()
    _save(queue, queue_path)
    save_source_registry(source_registry)
    save_company_registry(company_registry)
    return {
        "attempted": len(pending),
        "repaired": repaired,
        "failed": failed,
        "pending": sum(x.get("status") == "PENDING" for x in queue.get("items", {}).values()),
        "queue_path": str(queue_path),
    }


def summary(queue_path=QUEUE_PATH):
    queue = _load(queue_path)
    items = list((queue.get("items") or {}).values())
    return {
        "total": len(items),
        "pending": sum(x.get("status") == "PENDING" for x in items),
        "failed": sum(x.get("status") == "FAILED" for x in items),
        "repaired": sum(x.get("status") == "REPAIRED" for x in items),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--queue", default=str(QUEUE_PATH))
    parser.add_argument("--retry-state", default=str(RETRY_STATE_PATH))
    args = parser.parse_args()
    print(json.dumps(repair(args.limit, Path(args.queue), Path(args.retry_state)), indent=2))
