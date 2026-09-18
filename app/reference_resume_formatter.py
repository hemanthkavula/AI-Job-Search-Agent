from __future__ import annotations
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from app.resume_generator import ROOT, safe_name
import re

ACCENT=RGBColor(31,78,121); GRAY=RGBColor(89,89,89); BLUE="1F4E79"

def _run(r,size=9.2,bold=False,color=None,underline=False):
    r.font.name="Arial";r.font.size=Pt(size);r.bold=bold;r.underline=underline
    if color:r.font.color.rgb=color
    return r

def _compact(p,before=0,after=0,line=1.0):
    p.paragraph_format.space_before=Pt(before);p.paragraph_format.space_after=Pt(after);p.paragraph_format.line_spacing=line

def _section(doc,text):
    p=doc.add_paragraph();_compact(p,7,5);_run(p.add_run(text),10.5,True,ACCENT)
    pPr=p._p.get_or_add_pPr();pBdr=OxmlElement("w:pBdr");bottom=OxmlElement("w:bottom")
    bottom.set(qn("w:val"),"single");bottom.set(qn("w:sz"),"8");bottom.set(qn("w:space"),"2");bottom.set(qn("w:color"),BLUE);pBdr.append(bottom);pPr.append(pBdr)

def _company_header(doc,base):
    # Keep employer/date information in a normal paragraph so ATS/text parsers can
    # see the employer boundary. A right-aligned tab preserves the reference look
    # without using a table, text box, column, or other ATS-hostile structure.
    p=doc.add_paragraph();_compact(p,2,0)
    p.paragraph_format.tab_stops.add_tab_stop(Inches(7.45),WD_TAB_ALIGNMENT.RIGHT)
    _run(p.add_run(base["company"]),10,True)
    if base.get("location"):_run(p.add_run(" | "+base["location"]),9.2)
    _run(p.add_run("\t"+base["dates"]),9,False,GRAY)
    p=doc.add_paragraph();_compact(p,0,2);_run(p.add_run(base["title"]),9.5,True,ACCENT)

def canonical_resume_title(title):
    """Reduce noisy posting titles to the clean role title used on the resume/file."""
    raw=re.sub(r"\s+"," ",str(title or "")).strip()
    # Prefer the literal Data Engineer family phrase and preserve seniority immediately
    # before it. Everything after the core role (tech stack, location, promo text) is noise.
    m=re.search(r"(?i)\b(?:(principal|staff|lead|senior|sr\.?|junior|jr\.?)\s+)?data\s+engineer(?:ing)?\b",raw)
    if m:
        level=(m.group(1) or "").lower().rstrip(".")
        level={"sr":"Senior","jr":"Junior"}.get(level,level.title())
        core="Data Engineering" if re.search(r"(?i)data\s+engineering",m.group(0)) else "Data Engineer"
        return f"{level} {core}".strip()
    # For adjacent DE-family titles, strip common marketing prefixes and stack/location
    # suffixes while retaining the actual role name.
    cleaned=re.sub(r"(?i)^\s*(?:immediate interviews?|urgent(?: hiring)?|hiring now)\s*[-:|]\s*","",raw)
    cleaned=re.split(r"\s+(?:[-|/]\s*)(?=(?:airflow|dbt|kubernetes|openshift|aws|azure|gcp|snowflake|databricks|hybrid|remote|onsite|on-site)\b)",cleaned,1,flags=re.I)[0]
    return cleaned.strip(" -|:/") or "Senior Data Engineer"

def render_llm_resume(job,profile,generated,output_dir="generated/resumes"):
    """Formatting-only renderer. Generated resume wording is passed through unchanged."""
    doc=Document();s=doc.sections[0];s.top_margin=Inches(.42);s.bottom_margin=Inches(.42);s.left_margin=Inches(.48);s.right_margin=Inches(.48)
    doc.styles["Normal"].font.name="Arial";doc.styles["Normal"].font.size=Pt(9.2);doc.styles["Normal"].paragraph_format.space_after=Pt(0)
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;_compact(p,0,2);_run(p.add_run(profile["name"]),16,True,ACCENT)
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;_compact(p,0,3);_run(p.add_run(canonical_resume_title(job.title or profile.get("headline","Senior Data Engineer"))),11,False,ACCENT)
    c=profile.get("contact",{});p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;_compact(p,0,3)
    vals=[x for x in [c.get("phone"),c.get("email"),c.get("linkedin")] if x]
    for i,v in enumerate(vals):
        if i:_run(p.add_run("  |  "),9.2)
        link=("@" in v or "linkedin" in v.lower());_run(p.add_run(v),9.2,False,RGBColor(5,99,193) if link else None,link)
    _section(doc,"PROFESSIONAL SUMMARY");p=doc.add_paragraph();_compact(p,0,4,1.12);_run(p.add_run(generated.get("summary","")),9.35)
    _section(doc,"TECHNICAL SKILLS")
    for label,vals in generated.get("skills",{}).items():
        p=doc.add_paragraph();_compact(p,0,.5);_run(p.add_run(str(label)+": "),9.2,True);_run(p.add_run(", ".join(str(v) for v in vals)),9.2)
    _section(doc,"PROFESSIONAL EXPERIENCE")
    expected={x["company"]:x for x in profile["experience"]};limits={"Fidelity Investments":8,"Cigna Healthcare":7,"Target Corporation":6}
    for item in generated.get("experience",[]):
        base=expected.get(item.get("company"))
        if not base:continue
        _company_header(doc,base)
        for line in item.get("bullets",[])[:limits.get(base["company"],7)]:
            # Retain the standard Word List Bullet style so the internal auditor and
            # external ATS parsers identify these as experience bullets.
            p=doc.add_paragraph(style="List Bullet");p.paragraph_format.left_indent=Inches(.28);p.paragraph_format.first_line_indent=Inches(-.16);_compact(p,0,2,1.03);_run(p.add_run(str(line).strip()),9.15)
    _section(doc,"EDUCATION")
    for e in profile["education"]:
        p=doc.add_paragraph();_compact(p,0,1);_run(p.add_run(e["degree"]),9.5,True)
        p=doc.add_paragraph();_compact(p,0,1);_run(p.add_run(f"{e['school']} | {e['location']}    {e['start']} – {e['end']}"),9.2)
    out=ROOT/output_dir;out.mkdir(parents=True,exist_ok=True);pattern=profile.get("output",{}).get("resume_filename_pattern","Hemanth_Kavula_{Company}_{JobTitle}")
    clean_title=canonical_resume_title(job.title)
    stem=pattern.replace("{Company}",safe_name(job.company)).replace("{JobTitle}",safe_name(clean_title));path=out/f"{stem}.docx";doc.save(path);return str(path)
