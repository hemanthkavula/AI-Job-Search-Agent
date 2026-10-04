from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER_RESUME_PATH = ROOT / "data" / "master_resume.json"


def load_master_resume(path: str | Path = MASTER_RESUME_PATH) -> dict:
    """Load the user-designated master resume record."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    required = ("source", "identity", "style", "summary", "skills", "experience", "education")
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise RuntimeError("Master resume record is incomplete: " + ", ".join(missing))
    if data["source"].get("authority") != "user_uploaded_master":
        raise RuntimeError("Master resume record is not marked as user-authoritative")
    return data


def fixed_personal_facts(master: dict | None = None) -> dict:
    """Return immutable identity/chronology facts used by every resume."""
    master = master or load_master_resume()
    identity = master["identity"]
    return {
        "name": identity["name"],
        "headline": identity["headline"],
        "contact": dict(identity.get("contact") or {}),
        "employment_history": [
            {
                "company": row["company"],
                "location": row["location"],
                "title": row["title"],
                "dates": row["dates"],
            }
            for row in master["experience"]
        ],
        "education": [dict(row) for row in master["education"]],
    }


def master_resume_payload(master: dict | None = None) -> dict:
    """Return the exact content payload used for the unchanged-master route."""
    master = master or load_master_resume()
    return {
        "_master_mode": True,
        "summary": "\n\n".join(master["summary"]),
        "summary_emphasis": list(master.get("summary_emphasis") or []),
        "skills": {key: list(values) for key, values in master["skills"].items()},
        "experience": [
            {
                "company": row["company"],
                "bullets": list(row["bullets"]),
                "bullet_emphasis": [list(x) for x in row.get("bullet_emphasis") or []],
                "environment": row.get("environment", ""),
            }
            for row in master["experience"]
        ],
        "education": [dict(row) for row in master["education"]],
    }


def master_tailoring_base(master: dict | None = None) -> dict:
    """Return the truthful master content reservoir for hybrid tailoring.

    This is intentionally separate from fixed_personal_facts(). The hybrid
    writer may retain this user-authoritative content when a JD does not provide
    enough evidence to improve a section. New technologies that are absent from
    the master may only be introduced when they are supported by the current JD.
    """
    master = master or load_master_resume()
    return {
        "authority": master["source"].get("authority"),
        "summary_paragraphs": list(master["summary"]),
        "skills": {key: list(values) for key, values in master["skills"].items()},
        "experience": [
            {
                "company": row["company"],
                "bullets": list(row["bullets"]),
                "environment": row.get("environment", ""),
            }
            for row in master["experience"]
        ],
    }
