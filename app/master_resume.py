from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER_RESUME_PATH = ROOT / "data" / "master_resume.json"


def load_master_resume(path: str | Path = MASTER_RESUME_PATH) -> dict:
    """Load the user-designated master resume record.

    This file is the source of truth for the zero-target resume and for fixed
    identity/chronology used by tailored resumes. Technical content from the
    master is intentionally not exposed to the tailoring prompt.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    required = ("source", "identity", "style", "summary", "skills", "experience", "education")
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise RuntimeError("Master resume record is incomplete: " + ", ".join(missing))
    if data["source"].get("authority") != "user_uploaded_master":
        raise RuntimeError("Master resume record is not marked as user-authoritative")
    return data


def fixed_personal_facts(master: dict | None = None) -> dict:
    """Return only fixed personal/history facts safe to send to the resume writer.

    No master summary, skills, environments, bullets, or emphasis phrases are
    returned here. This is the technical-content firewall for JD tailoring.
    """
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
    """Return the exact content payload used when the JD yields zero targets."""
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
