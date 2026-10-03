from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "data" / "candidate_profile.json"

CANONICAL_TARGET_ROLES = (
    "Data Engineer",
    "Senior Data Engineer",
    "Analytics Engineer",
    "Data Platform Engineer",
    "Data Infrastructure Engineer",
    "Data Pipeline Engineer",
    "Data Warehouse Engineer",
    "ETL Engineer",
    "Big Data Engineer",
)


def _merge_target_roles(profile: dict) -> dict:
    """Keep runtime role intent aligned with the production Data Engineering family.

    The JSON profile remains the editable source of truth for user preferences, but
    older profile snapshots can omit newly approved adjacent DE titles. Merge the
    canonical production family at load time so scoring, diagnostics and future
    consumers cannot silently narrow discovery back to only literal Data Engineer
    titles. Existing user-entered roles are preserved in their original order.
    """
    preferences = profile.setdefault("preferences", {})
    existing = list(preferences.get("target_roles") or [])
    seen = {str(role).strip().lower() for role in existing}
    for role in CANONICAL_TARGET_ROLES:
        if role.lower() not in seen:
            existing.append(role)
            seen.add(role.lower())
    preferences["target_roles"] = existing
    return profile


def load_profile() -> dict:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return _merge_target_roles(profile)
