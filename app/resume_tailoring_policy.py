from __future__ import annotations

import math
import re

MODE_MASTER = "MASTER_UNCHANGED"
MODE_LIGHT = "JD_DRIVEN_LIGHT"
MODE_MODERATE = "JD_DRIVEN_MODERATE"
MODE_STRONG = "JD_DRIVEN_STRONG"
MODE_FULL = "JD_DRIVEN_FULL"

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

# The uploaded Word/PDF resume is a formatting template, not a technical-content
# reservoir for JD-tailored resumes. Nonzero-target modes therefore have no
# requirement to retain technical bullets from the template.
RETENTION_FLOORS = {
    MODE_MASTER: {"Fidelity Investments": 10, "Cigna Healthcare": 8, "Target Corporation": 8},
    MODE_LIGHT: {"Fidelity Investments": 0, "Cigna Healthcare": 0, "Target Corporation": 0},
    MODE_MODERATE: {"Fidelity Investments": 0, "Cigna Healthcare": 0, "Target Corporation": 0},
    MODE_STRONG: {"Fidelity Investments": 0, "Cigna Healthcare": 0, "Target Corporation": 0},
    MODE_FULL: {"Fidelity Investments": 0, "Cigna Healthcare": 0, "Target Corporation": 0},
}

# These ratios preserve roughly the same visual density as the two-page Word
# template while allowing all technical wording to come from the current JD.
SUMMARY_MIN_RATIO = {
    MODE_MASTER: 0.95,
    MODE_LIGHT: 0.65,
    MODE_MODERATE: 0.65,
    MODE_STRONG: 0.60,
    MODE_FULL: 0.60,
}

SKILLS_ROW_MIN_RATIO = {
    MODE_MASTER: 0.95,
    MODE_LIGHT: 0.25,
    MODE_MODERATE: 0.25,
    MODE_STRONG: 0.25,
    MODE_FULL: 0.25,
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
    statements = [
        x.strip()
        for x in re.split(r"[\n\r]+|(?<=[.!?])\s+", text or "")
        if x.strip()
    ]
    return sum(
        any(re.search(pattern, statement, flags=re.I) for pattern in ACTION_PATTERNS)
        for statement in statements
    )


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
    """Choose how much JD evidence is available for a JD-driven tailored resume.

    For any nonzero target count, the current JD is the technical-content source.
    The uploaded Word/PDF resume supplies format only. Zero targets retain the
    existing unchanged-master fallback so a weak/empty JD cannot manufacture
    unsupported technical content.
    """
    richness = jd_richness(job, coverage_plan)
    target_count = richness["target_count"]

    if target_count == 0:
        mode = MODE_MASTER
        reason = "No meaningful JD targets; use the unchanged master fallback rather than invent technical content."
    else:
        partial = (
            richness["source_tailoring_mode"] == "BASE_RESUME_CONSERVATIVE"
            or richness["description_complete"] is False
        )
        words = richness["word_count"]
        actions = richness["action_statement_count"]

        if target_count <= 2 or partial or (words < 180 and actions < 3):
            mode = MODE_LIGHT
            reason = "Limited JD evidence; create a conservative JD-driven resume using only explicit JD technical content."
        elif target_count <= 5 or (words < 350 and actions < 5):
            mode = MODE_MODERATE
            reason = "Moderate JD evidence; use the JD to drive the technical summary, skills, and selected experience coverage."
        elif target_count <= 9 or (words < 600 and actions < 8):
            mode = MODE_STRONG
            reason = "Rich JD evidence; use broad JD-driven technical coverage while preserving fixed history and employer domains."
        else:
            mode = MODE_FULL
            reason = "Rich, detailed JD; drive the technical resume from the JD while preserving fixed history, domain locks, and Word formatting."

    return {
        "mode": mode,
        "reason": reason,
        "richness": richness,
        "minimum_master_bullets_retained": dict(RETENTION_FLOORS[mode]),
        "summary_min_master_density_ratio": SUMMARY_MIN_RATIO[mode],
        "summary_max_master_density_ratio": 1.15,
        "skills_min_master_row_ratio": SKILLS_ROW_MIN_RATIO[mode],
        "minimum_jd_specific_experience_bullets": MIN_JD_EXPERIENCE_BULLETS[mode],
        "master_is_base": mode == MODE_MASTER,
        "word_template_is_format_only": mode != MODE_MASTER,
        "technical_content_source": "current_job_description" if mode != MODE_MASTER else "unchanged_master_fallback",
        "new_technology_requires_jd_evidence": mode != MODE_MASTER,
        "unchanged_master_bullets_should_be_verbatim": mode == MODE_MASTER,
    }


def minimum_skill_rows(master_skill_row_count: int, policy: dict) -> int:
    ratio = float(policy.get("skills_min_master_row_ratio") or 0)
    return max(1, math.ceil(master_skill_row_count * ratio))
