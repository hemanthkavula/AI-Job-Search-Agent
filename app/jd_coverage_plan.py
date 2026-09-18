from __future__ import annotations
import re
from app.resume_generator import jd_keywords, inferable_terms, jd_skill_terms

OPTIONAL_LANGUAGE_ALTERNATIVES={"Go","Rust","Scala","Java"}
CANONICAL={
    "Synapse Analytics":"Azure Synapse Analytics","Azure Synapse":"Azure Synapse Analytics",
    "Data Factory":"Azure Data Factory","ETL":"ETL/ELT","ELT":"ETL/ELT","CI/CD":"CI/CD Best Practices",
}
ALIASES={
    "Azure Synapse Analytics":("azure synapse analytics","azure synapse","synapse analytics"),
    "Azure Data Factory":("azure data factory","data factory","adf"),
    "BigQuery":("bigquery","google bigquery"),"Kubernetes":("kubernetes","k8s"),
    "Apache Kafka":("apache kafka","kafka"),"Apache Spark":("apache spark","spark","pyspark"),
    "Airflow":("airflow","apache airflow"),"Amazon Redshift":("amazon redshift","redshift"),
    "AWS Glue":("aws glue","glue"),"Snowflake":("snowflake",),"Docker":("docker",),
    "Terraform":("terraform",),"Git":("git","github","gitlab"),"Performance Tuning":("performance tuning","performance optimization"),
    "Data Governance":("data governance","governance"),"CI/CD Best Practices":("ci/cd","continuous integration","continuous delivery","continuous deployment"),
    "ETL/ELT":("etl","elt","etl/elt"),
}
REQUIRED_CUES=("required","requirements","must have","must-have","minimum qualifications","basic qualifications","proficiency","strong experience","hands-on","expertise")
PREFERRED_CUES=("preferred","nice to have","nice-to-have","bonus","plus","desired","preferred qualifications")
ALTERNATIVE_CUES=(" or ","and/or","one of","such as","e.g.")

def _canonical(term): return CANONICAL.get(term,term)
def _aliases(term): return ALIASES.get(term,(term.lower(),))
def _mentioned(line,term):
    low=line.lower()
    return any(re.search(r"(?<![a-z0-9])"+re.escape(a.lower())+r"(?![a-z0-9])",low) for a in _aliases(term))
def _profile_terms(profile):
    out=set(profile.get("skills",[]))
    for values in profile.get("skill_categories",{}).values(): out.update(values)
    for exp in profile.get("experience",[]):
        out.update(x.strip() for x in re.split(r"[,()]|\bAWS\b|\bAzure\b",exp.get("environment","")) if x.strip())
    return {_canonical(x) for x in out}
def _classify(term,description):
    lines=[x.strip() for x in re.split(r"[\n\r]+|(?<=[.!?])\s+",description or "") if _mentioned(x,term)]
    if not lines:return "mentioned"
    if any(any(c in x.lower() for c in PREFERRED_CUES) for x in lines):return "preferred"
    if any(any(c in x.lower() for c in REQUIRED_CUES) for x in lines):return "required"
    if any(any(c in x.lower() for c in ALTERNATIVE_CUES) for x in lines):return "alternative"
    return "material"

def build_coverage_plan(job,profile):
    """Build a truthful deterministic JD→candidate-evidence plan before any paid LLM call."""
    raw=list(dict.fromkeys(jd_keywords(job.description,profile)+inferable_terms(job.description)+jd_skill_terms(job.description)))
    targets=[]
    for term in raw:
        term=_canonical(term)
        if term not in targets:targets.append(term)
    if "Python" in targets: targets=[t for t in targets if t not in OPTIONAL_LANGUAGE_ALTERNATIVES]

    inventory=_profile_terms(profile)
    requirements=[]
    for term in targets:
        classification=_classify(term,job.description)
        supported=term in inventory
        requirements.append({"term":term,"classification":classification,"candidate_supported":supported,
                             "resume_action":"include_with_experience_evidence" if supported and classification in {"required","material"} else
                                             "include_if_helpful" if supported else "do_not_claim_as_experience"})

    must_cover=[r["term"] for r in requirements if r["candidate_supported"] and r["classification"] in {"required","material"}]
    preferred=[r["term"] for r in requirements if r["classification"]=="preferred"]
    alternatives=[r["term"] for r in requirements if r["classification"]=="alternative"]
    unsupported=[r["term"] for r in requirements if not r["candidate_supported"]]
    return {
        "targeted_terms":targets,"target_count":len(targets),"requirements":requirements,
        "must_cover_supported_terms":must_cover,"preferred_terms":preferred,"alternative_terms":alternatives,
        "unsupported_terms_do_not_claim":unsupported,
        "v1_instruction":(
            "Before writing V1, explicitly cover every term in must_cover_supported_terms using exact JD terminology "
            "where natural, normally in Technical Skills and with credible Professional Experience evidence. "
            "Preferred/alternative terms are not mandatory when another supported requirement satisfies the JD. "
            "Never invent unsupported experience. Preserve fixed identity, employers, titles, dates, education and domains."
        ),
    }
