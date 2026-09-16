import re

ALIASES = {
    "Amazon S3": ["s3", "amazon s3"],
    "Amazon EMR": ["emr", "amazon emr"],
    "Amazon Redshift": ["redshift", "amazon redshift"],
    "AWS Glue": ["glue", "aws glue"],
    "Azure Data Factory": ["adf", "azure data factory"],
    "Azure Synapse Analytics": ["synapse", "azure synapse"],
    "ADLS Gen2": ["adls", "adls gen2", "azure data lake storage"],
    "Event Hub": ["event hub", "event hubs"],
    "Apache Spark": ["spark", "apache spark"],
    "Apache Kafka": ["kafka", "apache kafka"],
    "PySpark": ["pyspark", "py spark"],
    "Great Expectations": ["great expectations"],
    "Azure Purview": ["purview", "azure purview"],
}

def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9+#. ]+", " ", (text or "").lower())

def _has_skill(skill: str, text: str) -> bool:
    variants=ALIASES.get(skill,[skill])
    return any(_norm(v) in text for v in variants)

def analyze_job(job, profile: dict) -> dict:
    text=_norm(f"{job.title} {job.description}")
    title=_norm(job.title)
    target_roles=[_norm(r) for r in profile["preferences"]["target_roles"]]
    role_match=any(role in title or title in role for role in target_roles) or ("data" in title and ("engineer" in title or "platform" in title))

    skills=profile["skills"]
    matched=[s for s in skills if _has_skill(s,text)]
    priority=profile["priority_skills"]
    matched_priority=[s for s in priority if _has_skill(s,text)]
    missing=[s for s in priority if s not in matched_priority]

    # Score against skills the JD actually asks for, with extra weight on core DE skills.
    skill_score=min(50, len(matched)*4 + len(matched_priority)*3)
    role_score=25 if role_match else 5

    employment=(job.employment_type or "").lower()
    desired=profile["preferences"]["employment_types"]
    employment_score=15 if not employment or any(x.lower() in employment for x in desired) else 0

    location_text=(job.location or "").lower()
    preferred=profile["preferences"]["preferred_locations"]
    location_score=10 if not location_text or any(x.lower() in location_text for x in preferred) or "remote" in location_text else 5

    score=min(100,skill_score+role_score+employment_score+location_score)
    decision="PRIORITY" if score>=85 else "REVIEW" if score>=65 else "SKIP"
    return {
        "company":job.company,"title":job.title,"score":score,"decision":decision,
        "matched_skills":matched,"missing_skills":missing,
        "reasons":[
            f"Role relevance: {'target/adjacent data engineering role' if role_match else 'weak title match'}",
            f"Matched {len(matched)} verified resume skills ({len(matched_priority)} priority skills)",
            f"Employment fit contribution: {employment_score}/15",
            f"Location fit contribution: {location_score}/10",
        ],
        "requires_review":True,
    }
