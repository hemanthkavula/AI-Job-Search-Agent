from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = Path(os.getenv("JOB_AGENT_RETRY_STATE", ROOT / "state" / "source_retry_state.json"))

TRANSIENT_MARKERS = (
    "timeout", "timed out", "incompleteread", "temporary", "connection reset",
    "connection aborted", "remote end closed", "429", "too many requests",
    "http 500", "http 502", "http 503", "http 504", "server error",
    "mcp unavailable", "mcp call failed",
)
HARD_MARKERS = (
    "http 404", "http 410", "not found", "invalid_pattern", "invalid pattern",
    "missing company_identifier", "missing client_id or search_url",
)


def _load(path=STATE_PATH):
    p = Path(path)
    if not p.exists():
        return {"version": 1, "units": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("units"), dict):
            return data
    except Exception:
        pass
    return {"version": 1, "units": {}}


def _save(data, path=STATE_PATH):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _status_row(key, value):
    if isinstance(value, dict):
        row = dict(value)
    else:
        provider, _, company = str(key).partition(":")
        row = {"source": provider, "company": company, "status": value}
    row.setdefault("source", str(key).partition(":")[0])
    row.setdefault("company", str(key).partition(":")[2])
    return row


def classify_failure(row):
    status = str(row.get("status") or "").upper()
    error = str(row.get("error") or row.get("health_status") or "").lower()
    if status == "SKIPPED_HARD_FAILURE":
        return "hard"
    if any(marker in error for marker in HARD_MARKERS):
        return "hard"
    if status in {"ERROR", "BACKOFF_TRANSIENT"}:
        if any(marker in error for marker in TRANSIENT_MARKERS):
            return "transient"
        # Unknown adapter errors are retried before being promoted to repair.
        return "transient"
    return None


def _backoff_hours(consecutive_failures):
    # First two failed production cycles retry on the next normal run.
    if consecutive_failures <= 2:
        return 0
    if consecutive_failures == 3:
        return 6
    if consecutive_failures == 4:
        return 12
    return 24


def update_from_cycle(source_unit_status, now=None, path=STATE_PATH):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    data = _load(path)
    units = data.setdefault("units", {})
    for key, value in (source_unit_status or {}).items():
        row = _status_row(key, value)
        status = str(row.get("status") or "").upper()
        entry = units.setdefault(key, {
            "source": row.get("source"),
            "company": row.get("company"),
            "consecutive_failures": 0,
        })
        entry["source"] = row.get("source") or entry.get("source")
        entry["company"] = row.get("company") or entry.get("company")
        entry["last_status"] = status
        entry["last_checked_at"] = row.get("checked_at") or now.isoformat()
        if status == "OK":
            entry["consecutive_failures"] = 0
            entry["last_success_at"] = now.isoformat()
            entry["next_retry_at"] = None
            entry["failure_class"] = None
            entry["last_error"] = None
            continue
        if status in {"SKIPPED_HARD_FAILURE", "ERROR", "BACKOFF_TRANSIENT"}:
            failure_class = classify_failure(row) or "transient"
            count = int(entry.get("consecutive_failures") or 0)
            # A BACKOFF record is not a fresh network failure; do not increment it.
            if status != "BACKOFF_TRANSIENT":
                count += 1
            entry["consecutive_failures"] = count
            entry["failure_class"] = failure_class
            entry["last_error"] = row.get("error") or row.get("health_status")
            if failure_class == "hard":
                entry["next_retry_at"] = None
                entry["repair_required"] = True
            else:
                delay = _backoff_hours(count)
                entry["next_retry_at"] = (now + timedelta(hours=delay)).isoformat() if delay else now.isoformat()
                # Repeated transient failures also deserve source rediscovery,
                # but only after three actual failed cycles.
                entry["repair_required"] = count >= 3
    data["updated_at"] = now.isoformat()
    _save(data, path)
    return data


def retry_decision(key, now=None, path=STATE_PATH):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    entry = (_load(path).get("units") or {}).get(key) or {}
    if entry.get("failure_class") == "hard" and entry.get("repair_required"):
        return {"attempt": False, "reason": "HARD_FAILURE_AWAITING_REPAIR", "entry": entry}
    value = entry.get("next_retry_at")
    if value:
        try:
            due = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
            if due > now:
                return {"attempt": False, "reason": "TRANSIENT_BACKOFF", "next_retry_at": due.isoformat(), "entry": entry}
        except Exception:
            pass
    return {"attempt": True, "reason": "DUE", "entry": entry}


def summary(path=STATE_PATH):
    units = (_load(path).get("units") or {})
    return {
        "tracked_units": len(units),
        "in_backoff": sum(not retry_decision(k, path=path)["attempt"] and retry_decision(k, path=path)["reason"] == "TRANSIENT_BACKOFF" for k in units),
        "repair_required": sum(bool(v.get("repair_required")) for v in units.values()),
    }
