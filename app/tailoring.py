def build_tailoring_plan(job, analysis: dict, profile: dict) -> dict:
    """Return truthful resume-edit guidance; never fabricate experience."""
    matched = analysis["matched_skills"]
    experiences = profile["experience"]
    relevant = []
    jd = job.description.lower()
    for exp in experiences:
        evidence = [item for item in exp["evidence"] if any(skill.lower() in item.lower() for skill in matched)]
        if evidence:
            relevant.append({"company": exp["company"], "evidence": evidence})

    return {
        "target_title": job.title,
        "company": job.company,
        "recommended_summary_focus": matched[:10],
        "verified_experience_to_emphasize": relevant,
        "missing_priority_terms": analysis["missing_skills"],
        "rules": [
            "Do not invent skills or experience.",
            "Do not change employer names, dates, education, certifications, or metrics.",
            "Use JD terminology only when supported by verified resume evidence.",
        ],
    }
