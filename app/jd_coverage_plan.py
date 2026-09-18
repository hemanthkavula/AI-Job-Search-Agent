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
    "Requirements Gathering":("requirements gathering","gathering requirements","gather requirements","business requirements","technical requirements","requirements analysis"),
    "Solution Design & Development":("solution design","solution development","design and development","design, development","design/develop","designed and developed"),
    "Solution Implementation & Support":("implementation and support","implement and support","implemented and supported","production support","application support"),
    "Data Integration Solutions":("data integration solutions","data integrations","integration solutions","data integration"),
    "Reusable Enterprise Solutions":("reusable enterprise solutions","reusable solutions","reusable data interfaces","reusable interfaces","reusable applications","reusable apps","repurposed"),
    "Proof of Concepts":("proof of concept","proof-of-concept","proof of concepts","proof-of-concepts","poc","prototype"),
    "Customer-Facing Solutions":("customer-facing solutions","customer facing solutions","customer-facing applications","customer facing applications","customer service delivery"),
    "Application Lifecycle Management":("application lifecycle management","enterprise alm","alm process","alm practices","build environments"),
    "Enterprise ALM":("enterprise alm","application lifecycle management","alm process","alm practices"),
    "Enterprise Data Interfaces":("enterprise data interfaces","data interfaces","enterprise interfaces"),
    "Cross-Functional Collaboration":("cross-functional","cross functional","collaborate with","partner with","liaise with","stakeholders"),
    "Continuous Improvement":("continuous improvement","recommend enhancements","process improvements","platform improvements","technology roadmap"),
    "Data Modeling":("data modeling","data modelling","data model","dimensional modeling","star schema"),
    "Testing & Quality Assurance":("unit testing","integration testing","performance testing","quality assurance","qa process","testing"),
    "Security & Governance":("security and governance","secure data","security policies","access control","data governance","compliance","regulated data"),
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
    """Build a deterministic JD-first keyword coverage plan before any paid LLM call."""
    raw=list(dict.fromkeys(jd_keywords(job.description,profile)+inferable_terms(job.description)+jd_skill_terms(job.description)))
    targets=[]
    for term in raw:
        term=_canonical(term)
        if term not in targets:targets.append(term)
    if "Python" in targets: targets=[t for t in targets if t not in OPTIONAL_LANGUAGE_ALTERNATIVES]

    requirements=[]
    for term in targets:
        classification=_classify(term,job.description)
        requirements.append({
            "term":term,
            "classification":classification,
            "resume_action":"include" if classification in {"required","material"} else "include_if_helpful"
        })

    must_cover=[r["term"] for r in requirements if r["classification"] in {"required","material"}]
    preferred=[r["term"] for r in requirements if r["classification"]=="preferred"]
    alternatives=[r["term"] for r in requirements if r["classification"]=="alternative"]
    return {
        "targeted_terms":targets,"target_count":len(targets),"requirements":requirements,
        "must_cover_terms":must_cover,"preferred_terms":preferred,"alternative_terms":alternatives,
        "v1_instruction":(
            "The complete JD is the technical tailoring source. Before writing V1, cover every material/required "
            "JD technology, responsibility, and material concept naturally across Summary, Technical Skills and relevant experience bullets. "
            "The master profile is not a technical-keyword whitelist. Preserve fixed factual history and do not "
            "invent certifications, employers, dates, education, numerical outcomes or specific accomplishments."
        ),
    }
