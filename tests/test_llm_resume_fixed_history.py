from types import SimpleNamespace

from app.llm_resume_writer import _fixed_history_profile, build_prompt


def _profile():
    return {
        "name":"Candidate",
        "headline":"Senior Data Engineer",
        "contact":{"email":"candidate@example.com"},
        "experience":[{
            "company":"Fidelity Investments","location":"Jersey City, NJ",
            "title":"Senior Data Engineer","dates":"Jan 2025 – Present",
            "environment":"LEGACY_ENVIRONMENT_SHOULD_NOT_LEAK",
            "evidence":["LEGACY_BULLET_SHOULD_NOT_LEAK"],
        }],
        "education":[{
            "degree":"Master of Science in Computer Science","school":"Rowan University",
            "location":"Glassboro, NJ","start":"Jan 2024","end":"Dec 2025",
            "coursework":["LEGACY_COURSEWORK_SHOULD_NOT_LEAK"],
        }],
        "skills":["LEGACY_SKILL_SHOULD_NOT_LEAK"],
        "skill_categories":{"Old":["LEGACY_SKILL_SHOULD_NOT_LEAK"]},
        "summary_source":["LEGACY_SUMMARY_SHOULD_NOT_LEAK"],
        "work_authorization":{"status":"SHOULD_NOT_BE_IN_RESUME_WRITER_PROMPT"},
        "certifications":["Verified Certification"],
    }


def test_fixed_history_profile_exposes_only_immutable_resume_facts():
    fixed=_fixed_history_profile(_profile())
    assert fixed["experience"] == [{
        "company":"Fidelity Investments","location":"Jersey City, NJ",
        "title":"Senior Data Engineer","dates":"Jan 2025 – Present",
    }]
    assert fixed["education"] == [{
        "degree":"Master of Science in Computer Science","school":"Rowan University",
        "location":"Glassboro, NJ","start":"Jan 2024","end":"Dec 2025",
    }]
    assert fixed["certifications"] == ["Verified Certification"]
    serialized=str(fixed)
    for forbidden in ("LEGACY_ENVIRONMENT_SHOULD_NOT_LEAK","LEGACY_BULLET_SHOULD_NOT_LEAK",
                      "LEGACY_SKILL_SHOULD_NOT_LEAK","LEGACY_SUMMARY_SHOULD_NOT_LEAK",
                      "SHOULD_NOT_BE_IN_RESUME_WRITER_PROMPT","LEGACY_COURSEWORK_SHOULD_NOT_LEAK"):
        assert forbidden not in serialized


def test_build_prompt_uses_sanitized_history_not_full_profile():
    job=SimpleNamespace(company="Example Co",title="Data Engineer",description="Build Python and SQL pipelines.")
    prompt=build_prompt(job,_profile(),coverage_plan={"requirements":[]})
    candidate=prompt["candidate_fixed_facts_and_background"]
    assert candidate == _fixed_history_profile(_profile())
    assert "skills" not in candidate
    assert "skill_categories" not in candidate
    assert "summary_source" not in candidate
    assert "work_authorization" not in candidate
    assert "environment" not in candidate["experience"][0]
    assert "evidence" not in candidate["experience"][0]


def test_limited_prompt_marks_partial_jd_and_forbids_inference():
    class Job:
        company="Example"
        title="Data Engineer"
        description="Build Spark pipelines in Python."
    profile={"name":"Candidate","contact":{},"experience":[],"education":[]}
    prompt=build_prompt(Job(),profile,coverage_plan={"target_count":2,"requirements":[]},mode="LIMITED")
    assert prompt["tailoring_policy"]["jd_completeness"]=="PARTIAL"
    assert prompt["tailoring_policy"]["partial_jd_evidence_boundary"] is True
    assert prompt["tailoring_policy"]["infer_missing_jd_content"] is False
    assert "PARTIAL JD" in prompt["task"]
