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

# Hybrid historical-credibility policy:
# - Fidelity is the current employer and is the primary JD-tailored section.
# - Cigna and Target remain anchored to the user's master-resume history.
# - Non-master modes may lightly reword older experience, but a majority of the
#   historical bullets must remain verbatim so the LLM cannot rewrite the entire
#   employment history simply to chase JD keywords.
RETENTION_FLOORS = {
    MODE_MASTER: {"Fidelity Investments": 10, "Cigna Healthcare": 8, "Target Corporation": 8},
    MODE_LIGHT: {"Fidelity Investments": 0, "Cigna Healthcare": 6, "Target Corporation": 6},
    MODE_MODERATE: {"Fidelity Investments": 0, "Cigna Healthcare": 5, "Target Corporation": 5},
    MODE_STRONG: {"Fidelity Investments": 0, "Cigna Healthcare": 5, "Target Corporation": 5},
    MODE_FULL: {"Fidelity Investments": 0, "Cigna Healthcare": 5, "Target Corporation": 5},
}

# Preserve roughly the same visual density as the two-page Word master while
# still allowing the current Fidelity section to carry JD-specific emphasis.
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
    """Choose the JD-tailoring strength while preserving truthful history.

    Zero meaningful JD targets use the unchanged master fallback. For nonzero
    targets, Fidelity is JD-driven, while Cigna and Target stay anchored to the
    master-resume historical baseline and may only be lightly aligned. New
    technologies require JD evidence and belong primarily in Fidelity; older
    employer cloud/timeline restrictions are enforced by the writer and audit.
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
            reason = "Limited JD evidence; tailor Fidelity conservatively and keep Cigna/Target strongly master-backed."
        elif target_count <= 5 or (words < 350 and actions < 5):
            mode = MODE_MODERATE
            reason = "Moderate JD evidence; tailor Fidelity to the JD while preserving the majority of Cigna/Target master bullets."
        elif target_count <= 9 or (words < 600 and actions < 8):
            mode = MODE_STRONG
            reason = "Rich JD evidence; use broad Fidelity coverage while preserving historical Cigna/Target credibility and domains."
        else:
            mode = MODE_FULL
            reason = "Rich, detailed JD; fully tailor Fidelity while retaining master-backed Cigna/Target history, cloud locks, and layout."

    return {
        "mode": mode,
        "reason": reason,
        "richness": richness,
        "minimum_master_bullets_retained": dict(RETENTION_FLOORS[mode]),
        "summary_min_master_density_ratio": SUMMARY_MIN_RATIO[mode],
        "summary_max_master_density_ratio": 1.15,
        "skills_min_master_row_ratio": SKILLS_ROW_MIN_RATIO[mode],
        "minimum_jd_specific_experience_bullets": MIN_JD_EXPERIENCE_BULLETS[mode],
        "master_is_base": True,
        "word_template_is_format_only": True,
        "technical_content_source": (
            "unchanged_master_fallback"
            if mode == MODE_MASTER
            else "hybrid_master_history_plus_current_jd"
        ),
        "new_technology_requires_jd_evidence": mode != MODE_MASTER,
        "unchanged_master_bullets_should_be_verbatim": mode == MODE_MASTER,
        "employer_tailoring_policy": {
            "Fidelity Investments": "primary_jd_tailored_current_employer",
            "Cigna Healthcare": "azure_master_baseline_light_alignment_only",
            "Target Corporation": "aws_master_baseline_light_alignment_only",
        },
        "historical_ai_policy": "AI-era technologies are allowed only in Fidelity when JD-supported",
    }


def minimum_skill_rows(master_skill_row_count: int, policy: dict) -> int:
    ratio = float(policy.get("skills_min_master_row_ratio") or 0)
    return max(1, math.ceil(master_skill_row_count * ratio))
