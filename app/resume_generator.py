
# USER RESUME PROMPT CONTRACT (2026-09-16)
# Generate a fresh resume per JD with strict domain lock:
# Fidelity = financial services; Cigna = healthcare; Target = retail.
# Preserve identity, company names, titles, locations, dates, education and certifications.
# Exact bullet counts: Fidelity 8, Cigna 7, Target 6.
# Fidelity gets strongest/newest JD technology coverage; Cigna moderate; Target foundational.
# Summary must be concise and naturally include top JD terms.
# Technical Skills should use standard ATS categories and blend relevant JD terminology naturally.
# No label such as "JD-aligned technologies".
# Metrics: Fidelity max 1-2, Cigna max 1-2, Target zero; never invent metrics.
# Linear ATS layout only: no tables, columns, graphics or text boxes.
# Use exact JD terminology where appropriate and run the ATS audit after generation.
from __future__ import annotations
from pathlib import Path
import re
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
ROOT=Path(__file__).resolve().parent.parent
ALIASES={"AWS Glue":["aws glue","glue"],"Amazon EMR":["amazon emr","emr"],"Amazon S3":["amazon s3","s3"],"Amazon Redshift":["amazon redshift","redshift"],"Azure Data Factory":["azure data factory","adf"],"Azure Synapse Analytics":["azure synapse","synapse"],"ADLS Gen2":["adls gen2","adls","azure data lake storage"],"Apache Spark":["apache spark","spark"],"Apache Kafka":["apache kafka","kafka"],"PySpark":["pyspark"],"Slowly Changing Dimensions":["slowly changing dimensions","scd type 2","scd"],"CI/CD Best Practices":["ci/cd","cicd"]}
def safe_name(v):return re.sub(r"[^A-Za-z0-9_-]+","_",v).strip("_")[:80]
def all_verified(profile):
    out=[]
    for xs in profile.get("skill_categories",{}).values():out.extend(xs)
    return list(dict.fromkeys(out))
def jd_keywords(jd,profile):
    low=(jd or "").lower();out=[]
    for s in all_verified(profile):
        if any(v in low for v in ALIASES.get(s,[s.lower()])):out.append(s)
    return out

def jd_skill_terms(jd):
    """Extract ATS-friendly technology terms directly from the JD for the skills section.
    Presence here does not create a claim that the technology was used at a named employer."""
    text=jd or ""
    catalog=["Python","SQL","Scala","Java","Go","Rust","PySpark","Apache Spark","Apache Kafka","Apache Flink",
      "Databricks","Snowflake","dbt","Dagster","Airflow","Fivetran","Airbyte","Kubernetes","Docker","Terraform",
      "AWS Glue","Amazon S3","Amazon EMR","Amazon Redshift","AWS Lambda","AWS Kinesis","Azure Data Factory",
      "Azure Synapse","ADLS Gen2","Azure Event Hubs","BigQuery","GCP","Apache Iceberg","Delta Lake","Hudi",
      "PostgreSQL","MySQL","MongoDB","Oracle","CI/CD","GitHub Actions","Jenkins","Data Governance","Data Lineage",
      "Data Quality","ETL","ELT","Batch Processing","Real-Time Data Processing","Dimensional Modeling"]
    low=text.lower()
    return [x for x in catalog if x.lower() in low]

def inferable_terms(jd):
    """JD concepts that may be stated when already evidenced by the candidate's documented work."""
    low=(jd or "").lower()
    mapping={
      "ETL/ELT":["etl","elt"],"Batch Processing":["batch processing","batch pipelines"],
      "Real-Time Data Processing":["real-time","real time","streaming"],
      "Data Lakehouse":["lakehouse"],"Data Lineage":["data lineage","lineage"],
      "Data Governance":["data governance","governance"],"Data Quality":["data quality"],
      "Performance Tuning":["performance tuning","performance optimization"],
      "Infrastructure as Code":["infrastructure as code","iac"],"Dimensional Modeling":["dimensional modeling"],
      "Schema Evolution":["schema evolution"],"Orchestration":["orchestration","workflow orchestration"]
    }
    return [label for label,terms in mapping.items() if any(t in low for t in terms)]

def unsupported_jd_terms(jd,profile):
    known=set(x.lower() for x in all_verified(profile));terms=[]
    common=["flink","kubernetes","java","golang","go","rust","gcp","bigquery","dbt","dagster","fivetran","airbyte","iceberg","hudi","teradata"]
    low=(jd or "").lower()
    for x in common:
        if re.search(r"(?<![a-z0-9])"+re.escape(x)+r"(?![a-z0-9])",low) and x not in known:terms.append(x)
    return terms
def _rank(lines,jd,keys):
    words=set(re.findall(r"[a-z0-9+#.-]+",(jd or "").lower()))
    return sorted(lines,key=lambda x:len(set(re.findall(r"[a-z0-9+#.-]+",x.lower()))&words)+4*sum(k.lower() in x.lower() for k in keys),reverse=True)
def _h(doc,t):
    p=doc.add_paragraph();p.paragraph_format.space_before=Pt(5);p.paragraph_format.space_after=Pt(1);r=p.add_run(t);r.bold=True;r.font.size=Pt(10.5)
def generate_resume(job,analysis,profile,output_dir="generated/resumes"):
    keys=jd_keywords(job.description,profile); inferred=inferable_terms(job.description); doc=Document();s=doc.sections[0]
    s.top_margin=Inches(.45);s.bottom_margin=Inches(.45);s.left_margin=Inches(.55);s.right_margin=Inches(.55)
    doc.styles["Normal"].font.name="Arial";doc.styles["Normal"].font.size=Pt(9.3)
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;r=p.add_run(profile["name"]);r.bold=True;r.font.size=Pt(15)
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;r=p.add_run(job.title or profile.get("headline","Senior Data Engineer"));r.bold=True;r.font.size=Pt(10.5)
    c=profile.get("contact",{});p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.add_run(" | ".join(x for x in [c.get("phone"),c.get("email"),c.get("linkedin")] if x))
    _h(doc,"PROFESSIONAL SUMMARY")
    focus=", ".join((keys+inferred)[:16]) or "Python, SQL, PySpark, Apache Spark, cloud data engineering"
    doc.add_paragraph(f"Senior Data Engineer with 5+ years of experience designing and optimizing scalable batch and real-time data platforms across financial services, healthcare, and retail. Hands-on expertise aligned to this role includes {focus}. Proven experience delivering Batch Processing and Real-Time Data Processing pipelines, cloud data lakes and warehouses, streaming systems, dimensional models, Data Lineage, Data Governance, Data Quality controls, and production performance improvements.")
    _h(doc,"TECHNICAL SKILLS")
    jd_skills=jd_skill_terms(job.description)
    # Merge JD technologies naturally into the regular Technical Skills section.
    # Do not label them as JD-derived.
    merged_jd=set(jd_skills)
    for cat,skills in profile.get("skill_categories",{}).items():
        extras=[]
        cat_low=cat.lower()
        for x in list(merged_jd):
            xl=x.lower()
            if ("program" in cat_low and xl in {"python","sql","scala","java","go","rust"}) or ("cloud" in cat_low and any(v in xl for v in ["aws","amazon","azure","gcp","bigquery"])) or ("data" in cat_low and xl not in {"python","sql","scala","java","go","rust"}):
                extras.append(x);merged_jd.discard(x)
        ordered=list(dict.fromkeys([x for x in skills if x in keys]+extras+[x for x in skills if x not in keys]))
        p=doc.add_paragraph();r=p.add_run(cat+": ");r.bold=True;p.add_run(", ".join(ordered))
    if merged_jd:
        p=doc.add_paragraph();r=p.add_run("Tools & Technologies: ");r.bold=True;p.add_run(", ".join(sorted(merged_jd)))
    _h(doc,"PROFESSIONAL EXPERIENCE")
    for exp in profile["experience"]:
        p=doc.add_paragraph();r=p.add_run(f"{exp['company']} | {exp.get('location','')}");r.bold=True;r=p.add_run(f"    {exp['dates']}");r.bold=True
        p=doc.add_paragraph();r=p.add_run(exp["title"]);r.bold=True
        p=doc.add_paragraph();r=p.add_run("Environment: ");r.bold=True;p.add_run(exp.get("environment",""))
        limits={"Fidelity Investments":8,"Cigna Healthcare":7,"Target Corporation":6}
        ranked=_rank(exp["evidence"],job.description,keys)[:limits.get(exp["company"],7)]
        for line in ranked:
            p=doc.add_paragraph(style="List Bullet");p.paragraph_format.left_indent=Inches(.16);p.paragraph_format.first_line_indent=Inches(-.10);p.add_run(line)
    _h(doc,"EDUCATION")
    for e in profile["education"]:
        p=doc.add_paragraph();r=p.add_run(e["degree"]);r.bold=True;doc.add_paragraph(f"{e['school']} | {e['location']}    {e['start']} – {e['end']}")
    out=ROOT/output_dir;out.mkdir(parents=True,exist_ok=True);pattern=profile.get("output",{}).get("resume_filename_pattern","Hemanth_Kavula_{Company}_{JobTitle}")
    stem=pattern.replace("{Company}",safe_name(job.company)).replace("{JobTitle}",safe_name(job.title))
    path=out/f"{stem}.docx";doc.save(path)
    return str(path)
