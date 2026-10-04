from __future__ import annotations

import math
import re

MODE_MASTER = "MASTER_UNCHANGED"
MODE_LIGHT = "HYBRID_LIGHT"
MODE_MODERATE = "HYBRID_MODERATE"
MODE_STRONG = "HYBRID_STRONG"
MODE_FULL = "HYBRID_FULL"

EMPLOYER_COUNTS = {"Fidelity Investments": 10, "Cigna Healthcare": 8, "Target Corporation": 8}

ACTION_PATTERNS = (
    r"\bdesign(?:ed|ing)?\b",
    r"\bbuild|\bbuilt\b",
    r"\bdevelop(?:ed|ing)?\b",
    r"\bimplement(?:ed|ing)?\b",
    r"\bengineer(?:ed|ing)?\b",
    r"\borchestrat(?:e|ed|ing|ion)\b",
    r"\bingest(?:ed|ing|ion)?\b",
    r"\btransform(?:ed|ing|ation)?\b",
    r"\boptimiz(?:e|ed|ing|ation)\b",
    r"\bmaintain(?:ed|ing)?\b",
    r"\bsupport(?:ed|ing)?\b",
    r"\bmonitor(?:ed|ing)?\b",
    r"\bmodel(?:ed|ing)?\b",
    r"\bintegrat(?:e|ed|ing|ion)\b",
)

# These are floors, not exact rewrite percentages. They prevent a short JD from
# causing the model to unnecessarily rewrite the whole user-authoritative resume.
RETENTION_FLOORS = {
    MODE_MASTER: {"Fidelity Investments": 10, "Cigna Healthcare": 8, "Target Corporation": 8},
    MODE_LIGHT: {"Fidelity Investments": 7, "Cigna Healthcare": 6, "Target Corporation": 6},
    MODE_MODERATE: {"Fidelity Investments": 5, "Cigna Healthcare": 4, "Target Corporation": 4},
    MODE_STRONG: {"Fidelity Investments": 2, "Cigna Healthcare": 2, "Target Corporation": 2},
    MODE_FULL: {"Fidelity Investments": 0, "Cigna Healthcare": 0, "Target Corporation": 0},
}

SUMMARY_MIN_RATIO = {
    MODE_MASTER: 0.95,
    MODE_LIGHT: 0.80,
    MODE_MODERATE: 0.72,
    MODE_STRONG: 0.65,
    MODE_FULL: 0.60,
}

SKILLS_ROW_MIN_RATIO = {
    MODE_MASTER: 0.95,
    MODE_LIGHT: 0.75,
    MODE_MODERATE: 0.65,
    MODE_STRONG: 0.55,
    MODE_FULL: 0.45,
}

MIN_JD_EXPERIENCE_BULLETS = {
    MODE_MASTER: 0,
    MODE_LIGHT: 2,
    MODE_MODERATE: 4,
    MODE_STRONG: 6,
    MODE_FULL: 6,
}


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z0-9+#./-]+\b", text or ""))


def _action_statement_count(text: str) -> int:
    statements = [x.strip() for x in re.split(r"[\n\r]+|(?<=[.!?])\s+", text or "") if x.strip()]
    return sum(any(re.search(pattern, statement, flags=re.I) for pattern in ACTION_PATTERNS) for statement in statements)


def jd_richness(job, coverage_plan: dict) -> dict:
    description = getattr(job, "description", "") or ""
    requirements = coverage_plan.get("requirements", []) or []
    material_count = sum(
        row.get("classification") in {"required", "material"}
        for row in requirements
        if isinstance(row, dict)
    )
    return {
        "word_count": _word_count(description),
        "character_count": len(description),
        "action_statement_count": _action_statement_count(description),
        "target_count": int(coverage_plan.get("target_count") or 0),
        "material_requirement_count": int(material_count),
        "description_complete": getattr(job, "description_complete", None),
        "description_usable": getattr(job, "description_usable", None),
        "source_tailoring_mode": getattr(job, "tailoring_mode", None),
    }


def determine_tailoring_policy(job, coverage_plan: dict) -> dict:
    """Choose how aggressively to tailor while keeping the master as the base.

    The decision intentionally uses both target count and JD richness. A short JD
    with five keywords is not treated the same as a detailed JD with five deeply
    described responsibilities.
    """
    richness = jd_richness(job, coverage_plan)
    target_count = richness["target_count"]

    if target_count == 0:
        mode = MODE_MASTER
        reason = "No meaningful JD targets; use the uploaded master unchanged."
    else:
        partial = (
            richness["source_tailoring_mode"] == "BASE_RESUME_CONSERVATIVE"
            or richness["description_complete"] is False
        )
        words = richness["word_count"]
        actions = richness["action_statement_count"]

        if target_count <= 2 or words < 180 or actions < 3 or partial:
            mode = MODE_LIGHT
            reason = "Few targets or a short/partial JD; keep most master content and make only evidence-supported changes."
        elif target_count <= 5 or words < 350 or actions < 5:
            mode = MODE_MODERATE
            reason = "Moderate JD evidence; tailor selected sections and bullets while retaining a strong master base."
        elif target_count <= 9 or words < 600 or actions < 8:
            mode = MODE_STRONG
            reason = "Rich JD evidence; make substantial changes but retain some master evidence for continuity."
        else:
            mode = MODE_FULL
            reason = "Rich, detailed JD with broad target coverage; JD may drive most content while preserving fixed history and format."

    return {
        "mode": mode,
        "reason": reason,
        "richness": richness,
        "minimum_master_bullets_retained": dict(RETENTION_FLOORS[mode]),
        "summary_min_master_density_ratio": SUMMARY_MIN_RATIO[mode],
        "summary_max_master_density_ratio": 1.25,
        "skills_min_master_row_ratio": SKILLS_ROW_MIN_RATIO[mode],
        "minimum_jd_specific_experience_bullets": MIN_JD_EXPERIENCE_BULLETS[mode],
        "master_is_base": True,
        "new_technology_requires_jd_evidence": True,
        "unchanged_master_bullets_should_be_verbatim": True,
    }


def minimum_skill_rows(master_skill_row_count: int, policy: dict) -> int:
    ratio = float(policy.get("skills_min_master_row_ratio") or 0)
    return max(1, math.ceil(master_skill_row_count * ratio))
