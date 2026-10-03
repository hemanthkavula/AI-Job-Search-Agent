from __future__ import annotations
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from app.resume_generator import ROOT, safe_name, clean_company_name
from datetime import datetime
from zoneinfo import ZoneInfo
import re

ACCENT=RGBColor(31,78,121); GRAY=RGBColor(89,89,89); LINK=RGBColor(5,99,193); BLUE="1F4E79"
MASTER_BULLET_COUNTS={"Fidelity Investments":10,"Cigna Healthcare":8,"Target Corporation":8}

def _run(r,size=10,bold=False,color=None,underline=False):
    r.font.name="Calibri";r.font.size=Pt(size);r.bold=bold;r.underline=underline
    if color:r.font.color.rgb=color
    return r

def _compact(p,before=0,after=0,line=1.0):
    p.paragraph_format.space_before=Pt(before);p.paragraph_format.space_after=Pt(after);p.paragraph_format.line_spacing=line

def _section(doc,text,after=5):
    p=doc.add_paragraph();_compact(p,10,after);p.paragraph_format.keep_with_next=True;_run(p.add_run(text),12,True,ACCENT)
    pPr=p._p.get_or_add_pPr();pBdr=OxmlElement("w:pBdr");bottom=OxmlElement("w:bottom")
    bottom.set(qn("w:val"),"single");bottom.set(qn("w:sz"),"8");bottom.set(qn("w:space"),"2");bottom.set(qn("w:color"),BLUE);pBdr.append(bottom);pPr.append(pBdr)
    return p

def _emphasis_runs(p,text,phrases,size=10,color=None):
    text=str(text or "")
    candidates=[str(x).strip() for x in (phrases or []) if str(x).strip()]
    seen=set();selected=[]
    for phrase in sorted(candidates,key=len,reverse=True):
        key=phrase.casefold()
        if key not in seen and key in text.casefold():seen.add(key);selected.append(phrase)
    if not selected:
        _run(p.add_run(text),size,False,color);return
    pattern=re.compile("("+"|".join(re.escape(x) for x in selected)+")",re.I)
    lookup={x.casefold() for x in selected}
    for part in pattern.split(text):
        if part:_run(p.add_run(part),size,part.casefold() in lookup,color)

def _summary_parts(text):
    text=str(text or "").strip();parts=[x.strip() for x in re.split(r"\n\s*\n",text) if x.strip()]
    if len(parts)>=2:return parts[:2]
    sentences=[x.strip() for x in re.split(r"(?<=[.!?])\s+",text) if x.strip()]
    if len(sentences)>=4:return [" ".join(sentences[:2])," ".join(sentences[2:])]
    if len(sentences)==3:return [sentences[0]," ".join(sentences[1:])]
    return [text] if text else []

def _all_skill_terms(generated):
    out=[]
    for vals in (generated.get("skills") or {}).values():out.extend(str(x) for x in (vals or []))
    return list(dict.fromkeys(out))

def _metric_terms(text):
    patterns=[r"~?\d+(?:\.\d+)?\s*[–-]\s*\d+(?:\.\d+)?\s*(?:GB/day|GB|TB|%|M|million)?",r"~?\d+(?:\.\d+)?\s*(?:GB/day|GB|TB|%|M|million)"]
    hits=[]
    for pat in patterns:hits.extend(m.group(0) for m in re.finditer(pat,text,re.I))
    return list(dict.fromkeys(hits))

def _fallback_emphasis(text,generated,max_terms=2):
    hits=[]
    for term in sorted(_all_skill_terms(generated),key=len,reverse=True):
        if len(term)>=3 and re.search(r"(?<![A-Za-z0-9])"+re.escape(term)+r"(?![A-Za-z0-9])",text,re.I):hits.append(term)
    hits=_metric_terms(text)+hits
    return list(dict.fromkeys(hits))[:max_terms]

def _company_header(doc,base):
    p=doc.add_paragraph();_compact(p,7,0);p.paragraph_format.keep_with_next=True;p.paragraph_format.tab_stops.add_tab_stop(Inches(7.45),WD_TAB_ALIGNMENT.RIGHT)
    _run(p.add_run(base["company"]),12,True);_run(p.add_run(" | "+base.get("location","")),10);_run(p.add_run("\t"+base["dates"]),10,False,GRAY)
    title=doc.add_paragraph();_compact(title,0,1);title.paragraph_format.keep_with_next=True;_run(title.add_run(base["title"]),11,True,ACCENT)
    roles=doc.add_paragraph();_compact(roles,0,1);roles.paragraph_format.keep_with_next=True;_run(roles.add_run("Roles & Responsibilities:"),10,True)
    return p,title,roles

def canonical_resume_title(title):
    raw=re.sub(r"\s+"," ",str(title or "")).strip()
    m=re.search(r"(?i)\b(?:(principal|staff|lead|senior|sr\.?|junior|jr\.?)\s+)?data\s+engineer(?:ing)?\b",raw)
    if m:
        level=(m.group(1) or "").lower().rstrip(".");level={"sr":"Senior","jr":"Junior"}.get(level,level.title())
        core="Data Engineering" if re.search(r"(?i)data\s+engineering",m.group(0)) else "Data Engineer";return f"{level} {core}".strip()
    cleaned=re.sub(r"(?i)^\s*(?:immediate interviews?|urgent(?: hiring)?|hiring now)\s*[-:|]\s*","",raw)
    cleaned=re.split(r"\s+(?:[-|/]\s*)(?=(?:airflow|dbt|kubernetes|openshift|aws|azure|gcp|snowflake|databricks|hybrid|remote|onsite|on-site)\b)",cleaned,1,flags=re.I)[0]
    return cleaned.strip(" -|:/") or "Senior Data Engineer"

def render_llm_resume(job,profile,generated,output_dir="generated/resumes"):
    """Render every base/JD-specific resume in the uploaded 2026-10-03 master style."""
    doc=Document();s=doc.sections[0];s.top_margin=Inches(.55);s.bottom_margin=Inches(.42);s.left_margin=Inches(.5);s.right_margin=Inches(.5)
    doc.styles["Normal"].font.name="Calibri";doc.styles["Normal"].font.size=Pt(10);doc.styles["Normal"].paragraph_format.space_after=Pt(0)
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;_compact(p,0,2.5);_run(p.add_run(profile["name"]),18,True,ACCENT)
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;_compact(p,0,3);_run(p.add_run(canonical_resume_title(job.title or profile.get("headline","Senior Data Engineer"))),13,False,ACCENT)
    c=profile.get("contact",{});p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;_compact(p,0,7)
    vals=[x for x in [c.get("phone"),c.get("email"),c.get("linkedin")] if x]
    for i,v in enumerate(vals):
        if i:_run(p.add_run(" | "),11)
        link=("@" in v or "linkedin" in v.lower());_run(p.add_run(v),11,False,LINK if link else None,link)

    _section(doc,"PROFESSIONAL SUMMARY",4)
    summary_emphasis=generated.get("summary_emphasis") or profile.get("summary_emphasis") or []
    parts=_summary_parts(generated.get("summary",""))
    for i,part in enumerate(parts):
        p=doc.add_paragraph();_compact(p,0,7 if i==0 and len(parts)>1 else 3,1.05)
        phrases=[x for x in summary_emphasis if str(x).casefold() in part.casefold()] or _fallback_emphasis(part,generated,5)
        _emphasis_runs(p,part,phrases,11)

    _section(doc,"TECHNICAL SKILLS",7)
    for label,vals in (generated.get("skills") or {}).items():
        p=doc.add_paragraph();_compact(p,0,.2,1.0);_run(p.add_run(str(label)+": "),10,True);_run(p.add_run(", ".join(str(v) for v in vals)),10)

    _section(doc,"PROFESSIONAL EXPERIENCE",4)
    expected={x["company"]:x for x in profile["experience"]}
    for item in generated.get("experience",[]):
        base=expected.get(item.get("company"))
        if not base:continue
        company_p,title_p,roles_p=_company_header(doc,base)
        first_bullet=None;emphasis_rows=item.get("bullet_emphasis") or base.get("bullet_emphasis") or []
        limit=(profile.get("master_resume_reference",{}).get("bullet_counts",{}) or MASTER_BULLET_COUNTS).get(base["company"],8)
        for idx,line in enumerate((item.get("bullets") or [])[:limit]):
            p=doc.add_paragraph(style="List Bullet");p.paragraph_format.left_indent=Inches(.50);p.paragraph_format.first_line_indent=Inches(-.18);p.paragraph_format.keep_together=True;_compact(p,0,3,1.0)
            # The master intentionally continues Fidelity bullets 9-10 on page two.
            if base["company"]=="Fidelity Investments" and idx==8:p.paragraph_format.page_break_before=True
            phrases=emphasis_rows[idx] if idx<len(emphasis_rows) and isinstance(emphasis_rows[idx],list) else []
            _emphasis_runs(p,str(line).strip(),phrases or _fallback_emphasis(str(line),generated,2),10)
            if first_bullet is None:first_bullet=p
        env=doc.add_paragraph();_compact(env,1,8);_run(env.add_run("Environment: "),10,True);_run(env.add_run(base.get("environment","")),10)
        if first_bullet is None:roles_p.paragraph_format.keep_with_next=False

    _section(doc,"EDUCATION",4)
    for e in profile["education"]:
        p=doc.add_paragraph();_compact(p,0,1);p.paragraph_format.keep_with_next=True;_run(p.add_run(e["degree"]),11,True)
        p=doc.add_paragraph();_compact(p,0,0);p.paragraph_format.tab_stops.add_tab_stop(Inches(7.45),WD_TAB_ALIGNMENT.RIGHT);_run(p.add_run(f"{e['school']} | {e['location']}"),10);_run(p.add_run("\t"+f"{e['start']} – {e['end']}"),10,False,GRAY)

    root=ROOT/output_dir;root.mkdir(parents=True,exist_ok=True);pattern=profile.get("output",{}).get("resume_filename_pattern","Hemanth_Kavula_{Company}_{JobTitle}")
    clean_title=canonical_resume_title(job.title);clean_company=clean_company_name(job.company)
    stem=pattern.replace("{Company}",safe_name(clean_company)).replace("{JobTitle}",safe_name(clean_title))
    timestamp=datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M%S")
    job_dir=root/f"{safe_name(clean_company)}_{safe_name(clean_title)}_{timestamp}";job_dir.mkdir(parents=True,exist_ok=True)
    path=job_dir/f"{stem}.docx";doc.save(path);return str(path)
