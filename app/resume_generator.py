from __future__ import annotations
from pathlib import Path
import re
from docx import Document
from docx.shared import Pt

ROOT=Path(__file__).resolve().parent.parent

def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+","_",value).strip("_")[:80]

def _rank_evidence(evidence: list[str], jd: str, skills: list[str]) -> list[str]:
    jd_l=jd.lower()
    def score(line: str):
        line_l=line.lower()
        return sum(2 for s in skills if s.lower() in line_l and s.lower() in jd_l) + sum(1 for token in set(re.findall(r"[a-z0-9+#.]+",line_l)) if token in jd_l)
    return sorted(evidence,key=score,reverse=True)

def generate_resume(job, analysis: dict, profile: dict, output_dir: str="generated/resumes") -> str:
    """Generate a truthful ATS-friendly DOCX from verified profile evidence."""
    doc=Document()
    styles=doc.styles
    styles["Normal"].font.name="Arial"
    styles["Normal"].font.size=Pt(10)

    p=doc.add_paragraph()
    run=p.add_run(profile["name"]); run.bold=True; run.font.size=Pt(16)
    p.alignment=1
    p=doc.add_paragraph(profile.get("headline","Senior Data Engineer")); p.alignment=1

    doc.add_heading("PROFESSIONAL SUMMARY",level=1)
    focus=", ".join(analysis["matched_skills"][:10])
    doc.add_paragraph(
        f"Senior Data Engineer with 5+ years of experience building scalable batch and real-time data platforms across financial services, healthcare, and retail. "
        f"Hands-on experience aligned to this role includes {focus}. Experienced in cloud data lakes, warehouses, distributed processing, streaming, data modeling, quality, and production optimization."
    )

    doc.add_heading("TECHNICAL SKILLS",level=1)
    # Reorder only; never add JD skills absent from the verified profile.
    matched=analysis["matched_skills"]
    remaining=[s for s in profile["skills"] if s not in matched]
    doc.add_paragraph(", ".join(matched+remaining))

    doc.add_heading("PROFESSIONAL EXPERIENCE",level=1)
    for exp in profile["experience"]:
        p=doc.add_paragraph()
        r=p.add_run(f"{exp['company']} | {exp['title']} | {exp['dates']}"); r.bold=True
        for item in _rank_evidence(exp["evidence"],job.description,matched):
            doc.add_paragraph(item,style="List Bullet")

    doc.add_heading("EDUCATION",level=1)
    for edu in profile["education"]:
        doc.add_paragraph(f"{edu['degree']} — {edu['school']}, {edu['location']} | {edu['start']} – {edu['end']}")

    out=ROOT/output_dir
    out.mkdir(parents=True,exist_ok=True)
    path=out/f"{safe_name(job.company)}_{safe_name(job.title)}_Hemanth_Kavula.docx"
    doc.save(path)
    return str(path)
