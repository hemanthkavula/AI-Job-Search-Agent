from __future__ import annotations
from pathlib import Path
import re
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION

ROOT=Path(__file__).resolve().parent.parent

def safe_name(v): return re.sub(r"[^A-Za-z0-9_-]+","_",v).strip("_")[:80]

def _tokens(text):
    return set(re.findall(r"[a-z0-9+#.]+",(text or "").lower()))

def _rank(lines,jd):
    jt=_tokens(jd)
    return sorted(lines,key=lambda x:len(_tokens(x)&jt),reverse=True)

def _heading(doc,text):
    p=doc.add_paragraph()
    p.paragraph_format.space_before=Pt(5); p.paragraph_format.space_after=Pt(2)
    r=p.add_run(text); r.bold=True; r.font.size=Pt(10.5)
    return p

def generate_resume(job,analysis,profile,output_dir="generated/resumes"):
    """Preserve the uploaded resume's structure; tailor only emphasis/order using verified content."""
    doc=Document()
    sec=doc.sections[0]
    sec.top_margin=Inches(.42); sec.bottom_margin=Inches(.42); sec.left_margin=Inches(.55); sec.right_margin=Inches(.55)
    normal=doc.styles["Normal"]; normal.font.name="Arial"; normal.font.size=Pt(9.2)
    normal.paragraph_format.space_after=Pt(1.5)

    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run(profile["name"]); r.bold=True; r.font.size=Pt(15)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run(job.title if job.title else profile.get("headline","Senior Data Engineer")); r.bold=True; r.font.size=Pt(10.5)
    c=profile.get("contact",{})
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(" | ".join(x for x in [c.get("phone"),c.get("email"),c.get("linkedin")] if x))

    _heading(doc,"PROFESSIONAL SUMMARY")
    matched=analysis.get("matched_skills",[])
    focus=", ".join(matched[:8])
    base=profile.get("summary_source",[])
    summary=(base[0] if base else "Senior Data Engineer with 5+ years of experience building high-scale data platforms and real-time pipelines.")
    if focus:
        summary += f" Strong hands-on alignment for this role includes {focus}."
    if len(base)>2: summary += " "+base[2]
    if len(base)>3: summary += " "+base[3]
    doc.add_paragraph(summary)

    _heading(doc,"TECHNICAL SKILLS")
    jd=(job.description or "").lower()
    for cat,skills in profile.get("skill_categories",{}).items():
        ordered=sorted(skills,key=lambda s:(s.lower() not in jd, skills.index(s)))
        p=doc.add_paragraph()
        r=p.add_run(f"{cat}: "); r.bold=True
        p.add_run(", ".join(ordered))

    _heading(doc,"PROFESSIONAL EXPERIENCE")
    for exp in profile["experience"]:
        p=doc.add_paragraph()
        r=p.add_run(f"{exp['company']} | {exp.get('location','')}"); r.bold=True
        r=p.add_run(f"    {exp['dates']}"); r.bold=True
        p=doc.add_paragraph(); r=p.add_run(exp["title"]); r.bold=True
        p=doc.add_paragraph(); r=p.add_run("Environment: "); r.bold=True; p.add_run(exp.get("environment",""))
        for line in _rank(exp["evidence"],job.description):
            p=doc.add_paragraph(style="List Bullet")
            p.paragraph_format.left_indent=Inches(.16); p.paragraph_format.first_line_indent=Inches(-.10)
            p.add_run(line)

    _heading(doc,"EDUCATION")
    for edu in profile["education"]:
        p=doc.add_paragraph(); r=p.add_run(edu["degree"]); r.bold=True
        doc.add_paragraph(f"{edu['school']} | {edu['location']}    {edu['start']} – {edu['end']}")

    out=ROOT/output_dir; out.mkdir(parents=True,exist_ok=True)
    path=out/f"{safe_name(job.company)}_{safe_name(job.title)}_Hemanth_Kavula.docx"
    doc.save(path); return str(path)
