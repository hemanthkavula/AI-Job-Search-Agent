from __future__ import annotations
from pathlib import Path
import re
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

ROOT=Path(__file__).resolve().parent.parent
ALIASES={
 "AWS Glue":["aws glue","glue"],"Amazon EMR":["amazon emr","emr"],"Amazon S3":["amazon s3","s3"],
 "Amazon Redshift":["amazon redshift","redshift"],"Azure Data Factory":["azure data factory","adf"],
 "Azure Synapse Analytics":["azure synapse analytics","azure synapse","synapse"],"ADLS Gen2":["adls gen2","adls","azure data lake storage gen2"],
 "Apache Spark":["apache spark","spark"],"Apache Kafka":["apache kafka","kafka"],"PySpark":["pyspark"],
 "Slowly Changing Dimensions":["slowly changing dimensions","scd","scd type 2"],"CI/CD Best Practices":["ci/cd","cicd"]
}

def safe_name(v): return re.sub(r"[^A-Za-z0-9_-]+","_",v).strip("_")[:80]
def _present(skill,jd):
    low=(jd or "").lower()
    return any(x in low for x in ALIASES.get(skill,[skill.lower()]))

def _all_verified(profile):
    vals=[]
    for xs in profile.get("skill_categories",{}).values(): vals.extend(xs)
    return list(dict.fromkeys(vals))

def _rank(lines,jd):
    words=set(re.findall(r"[a-z0-9+#.-]+",(jd or "").lower()))
    return sorted(lines,key=lambda x:len(set(re.findall(r"[a-z0-9+#.-]+",x.lower()))&words),reverse=True)

def _h(doc,t):
    p=doc.add_paragraph(); p.paragraph_format.space_before=Pt(4); p.paragraph_format.space_after=Pt(1)
    r=p.add_run(t); r.bold=True; r.font.size=Pt(10.5)

def generate_resume(job,analysis,profile,output_dir="generated/resumes"):
    """JD-targeted ATS resume using the uploaded master resume as the immutable factual source."""
    doc=Document(); s=doc.sections[0]
    s.top_margin=Inches(.38); s.bottom_margin=Inches(.38); s.left_margin=Inches(.5); s.right_margin=Inches(.5)
    doc.styles["Normal"].font.name="Arial"; doc.styles["Normal"].font.size=Pt(9)
    verified=_all_verified(profile)
    jd_skills=[x for x in verified if _present(x,job.description)]

    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run(profile["name"]); r.bold=True; r.font.size=Pt(15)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run(profile.get("headline","Senior Data Engineer")); r.bold=True; r.font.size=Pt(10.5)
    c=profile.get("contact",{}); p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(" | ".join(x for x in [c.get("phone"),c.get("email"),c.get("linkedin")] if x))

    _h(doc,"PROFESSIONAL SUMMARY")
    top=", ".join(jd_skills[:12])
    domain="financial services, healthcare, and retail"
    doc.add_paragraph(
      f"Senior Data Engineer with 5+ years of experience designing, building, and optimizing scalable batch and real-time data platforms across {domain}. "
      f"Strong hands-on expertise in {top if top else 'Python, SQL, PySpark, Apache Spark, cloud data engineering, streaming, and data warehousing'}. "
      "Proven experience delivering high-volume ETL/ELT pipelines, cloud data lakes, dimensional data models, streaming solutions, data quality controls, and production performance improvements. "
      "Experienced partnering with analytics, risk, compliance, clinical, and operations stakeholders to deliver reliable, analytics-ready data products."
    )

    _h(doc,"TECHNICAL SKILLS")
    for cat,skills in profile.get("skill_categories",{}).items():
        # Exact JD terms first, then retain the full verified category for ATS breadth.
        ordered=[x for x in skills if x in jd_skills]+[x for x in skills if x not in jd_skills]
        p=doc.add_paragraph(); rr=p.add_run(cat+": "); rr.bold=True; p.add_run(", ".join(ordered))

    _h(doc,"PROFESSIONAL EXPERIENCE")
    for exp in profile["experience"]:
        p=doc.add_paragraph(); rr=p.add_run(f"{exp['company']} | {exp.get('location','')}"); rr.bold=True
        rr=p.add_run(f"    {exp['dates']}"); rr.bold=True
        p=doc.add_paragraph(); rr=p.add_run(exp["title"]); rr.bold=True
        p=doc.add_paragraph(); rr=p.add_run("Environment: "); rr.bold=True; p.add_run(exp.get("environment",""))
        for line in _rank(exp["evidence"],job.description):
            p=doc.add_paragraph(style="List Bullet"); p.paragraph_format.left_indent=Inches(.15); p.paragraph_format.first_line_indent=Inches(-.1)
            p.add_run(line)

    _h(doc,"EDUCATION")
    for e in profile["education"]:
        p=doc.add_paragraph(); rr=p.add_run(e["degree"]); rr.bold=True
        doc.add_paragraph(f"{e['school']} | {e['location']}    {e['start']} – {e['end']}")

    out=ROOT/output_dir; out.mkdir(parents=True,exist_ok=True)
    path=out/f"{safe_name(job.company)}_{safe_name(job.title)}_Hemanth_Kavula.docx"; doc.save(path); return str(path)
