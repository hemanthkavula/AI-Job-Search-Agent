from pathlib import Path
import shutil

from app.reference_resume_formatter import WORD_TEMPLATE_PATH
from app.resume_pagination import enforce_experience_start_rule, validate_experience_start_rule


def test_employer_start_requires_first_bullet_without_locking_later_bullets(tmp_path):
    target = Path(tmp_path) / "resume.docx"
    shutil.copyfile(WORD_TEMPLATE_PATH, target)

    applied = enforce_experience_start_rule(target)
    assert applied["passed"], applied["reasons"]

    validated = validate_experience_start_rule(target)
    assert validated["passed"], validated["reasons"]
    assert validated["policy"] == (
        "aligned employer header/title/roles plus complete first bullet must start together"
    )


def test_pagination_policy_is_idempotent(tmp_path):
    target = Path(tmp_path) / "resume.docx"
    shutil.copyfile(WORD_TEMPLATE_PATH, target)

    first = enforce_experience_start_rule(target)
    second = enforce_experience_start_rule(target)

    assert first["passed"], first["reasons"]
    assert second["passed"], second["reasons"]
    assert validate_experience_start_rule(target)["passed"]
