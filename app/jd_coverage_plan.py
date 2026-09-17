from __future__ import annotations

from app.resume_generator import jd_keywords, inferable_terms, jd_skill_terms
from app.llm_resume_writer import _jd_requested_extended

OPTIONAL_LANGUAGE_ALTERNATIVES={"Go","Rust","Scala","Java"}

CANONICAL={
    "Synapse Analytics":"Azure Synapse Analytics",
    "Azure Synapse":"Azure Synapse Analytics",
    "Data Factory":"Azure Data Factory",
    "ETL":"ETL/ELT",
    "ELT":"ETL/ELT",
    "CI/CD":"CI/CD Best Practices",
}

def _canonical(term):
    return CANONICAL.get(term,term)

def build_coverage_plan(job,profile):
    """Build the deterministic ATS target plan before the paid LLM call."""
    raw=list(dict.fromkeys(
        jd_keywords(job.description,profile)
        + inferable_terms(job.description)
        + jd_skill_terms(job.description)
    ))
    targets=[]
    for term in raw:
        term=_canonical(term)
        if term not in targets:targets.append(term)

    # Python satisfies common alternative-language lists; do not force every
    # alternative language into a resume.
    if "Python" in targets:
        targets=[t for t in targets if t not in OPTIONAL_LANGUAGE_ALTERNATIVES]

    extended=_jd_requested_extended(job.description)
    baseline=set()
    for values in profile.get("skill_categories",{}).values():
        baseline.update(values)

    confirmed_extended=set(extended)
    supported=[t for t in targets if t in baseline or t in confirmed_extended or t in inferable_terms(job.description)]
    needs_careful_evidence=[t for t in targets if t not in supported]

    return {
        "targeted_terms":targets,
        "target_count":len(targets),
        "confirmed_extended_requested":extended,
        "supported_or_inferable_targets":supported,
        "targets_requiring_careful_evidence":needs_careful_evidence,
        "v1_instruction":(
            "Plan V1 against every targeted term before writing. Cover supported required JD terminology "
            "naturally across summary, skills, and experience. Confirmed extended technologies explicitly "
            "requested by the JD may be used as hands-on evidence in a coherent employer/domain context. "
            "Do not fabricate unsupported technologies merely to achieve a score."
        ),
    }
