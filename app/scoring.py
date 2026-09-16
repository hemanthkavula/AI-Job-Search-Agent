import re

def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9+#. ]+", " ", text.lower())

def analyze_job(job, profile: dict) -> dict:
    text = _norm(f"{job.title} {job.description}")
    target_roles = [r.lower() for r in profile["preferences"]["target_roles"]]
    role_match = any(role in job.title.lower() for role in target_roles)

    skills = profile["skills"]
    matched = [s for s in skills if _norm(s) in text]
    missing = [s for s in profile["priority_skills"] if _norm(s) not in text]

    skill_score = min(55, round(55 * len(matched) / max(1, len(skills))))
    role_score = 20 if role_match else 5

    employment = (job.employment_type or "").lower()
    desired = profile["preferences"]["employment_types"]
    employment_score = 15 if not employment or any(x.lower() in employment for x in desired) else 0

    location_text = (job.location or "").lower()
    preferred = profile["preferences"]["preferred_locations"]
    location_score = 10 if not location_text or any(x.lower() in location_text for x in preferred) or "remote" in location_text else 5

    score = min(100, skill_score + role_score + employment_score + location_score)
    decision = "PRIORITY" if score >= 85 else "REVIEW" if score >= 70 else "SKIP"

    reasons = [
        f"Role relevance: {'target role' if role_match else 'partial/non-exact title match'}",
        f"Matched {len(matched)} resume skills",
        f"Employment fit contribution: {employment_score}/15",
        f"Location fit contribution: {location_score}/10",
    ]
    return {
        "company": job.company,
        "title": job.title,
        "score": score,
        "decision": decision,
        "matched_skills": matched,
        "missing_skills": missing,
        "reasons": reasons,
        "requires_review": True,
    }
