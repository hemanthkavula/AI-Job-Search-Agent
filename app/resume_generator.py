from __future__ import annotations
from pathlib import Path
import re
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

ROOT=Path(__file__).resolve().parent.parent
STOP={"the","and","with","for","from","that","this","you","our","are","will","using","into","data","engineer","engineering","experience","years","work","team"}

def safe_name(v): return re.sub(r"[^A-Za-z0-9_-]+","_",v).strip("_")[:80]
def _tokens(text): return set(re.findall(r"[a-z][a-z0-9+#.-]{1,}",(text or "").lower()))-STOP

def jd_keywords(jd, profile):
    text=(jd or "").lower(); verified=[]
    # Only ATS keywords supported by the master resume/profile may be inserted.
    pool=[]
    for skills in profile.get("skill_categories",{}).values(): pool.extend(skills)
    pool += profile.get("skills",[])
    aliases={"Amazon S3":["s3"],"Amazon EMR":["emr"],"Amazon Redshift":["redshift"],"AWS Glue":["glue"],
      "Azure Data Factory":["adf"],"Azure Synapse Analytics":["synapse"],"Apache Spark":["spark"],
      "Apache Kafka":["kafka"],"ADLS Gen2":["adls"],"Event Hub":["event hub"],"Slowly Changing Dimensions":["scd","scd type 2"]}
    for skill in dict.fromkeys(pool):
        variants=[skill.lower()]+aliases.get(skill,[])
        if any(v in text for v in variants): verified.append(skill)
    return verified

def _rank(lines,jd,keywords):
    jt=_tokens(jd)
    def score(line):
        low=line.lower()
        return len(_tokens(line)&jt)+sum(4 for k in keywords if k.lower() in low)
    return sorted(lines,key=score,reverse=True)

def _heading(doc,text):
    p=doc.add_paragraph(); p.paragraph_format.space_before=Pt(4); p.paragraph_format.space_after=Pt(1)
    r=p.add_run(text); r.bold=True; r.font.size=Pt(10.5)

def generate_resume(job,analysis,profile,output_dir="generated/resumes"):
    """ATS-first resume preserving master format and adding only verified JD keywords."""
    doc=Document(); sec=doc.sections[0]
    sec.top_margin=Inches(.38); sec.bottom_margin=Inches(.38); sec.left_margin=Inches(.52); sec.right_margin=Inches(.52)
    normal=doc.styles["Normal"]; normal.font.name="Arial"; normal.font.size=Pt(9)
    normal.paragraph_format.space_after=Pt(1.2)

    keywords=jd_keywords(job.description,profile)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run(profile["name"]); r.bold=True; r.font.size=Pt(15)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run(job.title or profile.get("headline","Senior Data Engineer")); r.bold=True; r.font.size=Pt(10.5)
    c=profile.get("contact",{}); p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(" | ".join(x for x in [c.get("phone"),c.get("email"),c.get("linkedin")] if x))

    _heading(doc,"PROFESSIONAL SUMMARY")
    base=profile.get("summary_source",[])
    focus=", ".join(keywords[:12])
    summary=(base[0] if base else "Senior Data Engineer with 5+ years of experience building high-scale data platforms and real-time pipelines.")
    if focus: summary += f" Core technologies relevant to this position include {focus}."
    summary += " "+(base[2] if len(base)>2 else "")+" "+(base[3] if len(base)>3 else "")
    doc.add_paragraph(summary.strip())

    _heading(doc,"TECHNICAL SKILLS")
    jd=(job.description or "").lower()
    for cat,skills in profile.get("skill_categories",{}).items():
        ordered=sorted(skills,key=lambda s:(s not in keywords, s.lower() not in jd))
        p=doc.add_paragraph(); r=p.add_run(f"{cat}: "); r.bold=True; p.add_run(", ".join(ordered))

    _heading(doc,"PROFESSIONAL EXPERIENCE")
    for exp in profile["experience"]:
        p=doc.add_paragraph(); r=p.add_run(f"{exp['company']} | {exp.get('location','')}"); r.bold=True
        r=p.add_run(f"    {exp['dates']}"); r.bold=True
        p=doc.add_paragraph(); r=p.add_run(exp["title"]); r.bold=True
        p=doc.add_paragraph(); r=p.add_run("Environment: "); r.bold=True; p.add_run(exp.get("environment",""))
        for line in _rank(exp["evidence"],job.description,keywords):
            p=doc.add_paragraph(style="List Bullet"); p.paragraph_format.left_indent=Inches(.16); p.paragraph_format.first_line_indent=Inches(-.10)
            p.add_run(line)

    _heading(doc,"EDUCATION")
    for edu in profile["education"]:
        p=doc.add_paragraph(); r=p.add_run(edu["degree"]); r.bold=True
        doc.add_paragraph(f"{edu['school']} | {edu['location']}    {edu['start']} – {edu['end']}")

    out=ROOT/output_dir; out.mkdir(parents=True,exist_ok=True)
    path=out/f"{safe_name(job.company)}_{safe_name(job.title)}_Hemanth_Kavula.docx"; doc.save(path); return str(path)
