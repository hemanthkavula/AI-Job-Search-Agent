from __future__ import annotations
from pathlib import Path
import os, subprocess, shutil
from xml.sax.saxutils import escape
from docx import Document
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

def _native_convert(src: Path, target: Path) -> bool:
    """Prefer a real office renderer so PDF layout matches the DOCX."""
    if os.name=="nt":
        ps = (
          "$w=New-Object -ComObject Word.Application;"
          "$w.Visible=$false;"
          f"$d=$w.Documents.Open('{str(src).replace(chr(39), chr(39)*2)}');"
          f"$d.SaveAs([ref]'{str(target).replace(chr(39), chr(39)*2)}',[ref]17);"
          "$d.Close();$w.Quit()"
        )
        try:
            subprocess.run(["powershell","-NoProfile","-Command",ps],check=True,timeout=60,capture_output=True)
            if target.exists() and target.stat().st_size>0:return True
        except Exception:pass
    office=shutil.which("libreoffice") or shutil.which("soffice")
    if office:
        try:
            subprocess.run([office,"--headless","--convert-to","pdf","--outdir",str(target.parent),str(src)],check=True,timeout=60,capture_output=True)
            if target.exists() and target.stat().st_size>0:return True
        except Exception:pass
    return False

def convert_docx_to_pdf(docx_path: str) -> str | None:
    """Convert DOCX to PDF, preferring Word/LibreOffice for layout fidelity.
    ReportLab is retained only as a portability fallback."""
    src=Path(docx_path).resolve(); target=src.with_suffix(".pdf")
    if _native_convert(src,target):
        return str(target)
    doc=Document(str(src))
    styles=getSampleStyleSheet()
    normal=ParagraphStyle("ResumeNormal",parent=styles["Normal"],fontName="Helvetica",fontSize=8.8,leading=10.4,spaceAfter=2)
    center=ParagraphStyle("ResumeCenter",parent=normal,alignment=TA_CENTER)
    heading=ParagraphStyle("ResumeHeading",parent=normal,fontName="Helvetica-Bold",fontSize=10,leading=11,spaceBefore=4,spaceAfter=2)
    bullet=ParagraphStyle("ResumeBullet",parent=normal,leftIndent=12,firstLineIndent=-7,bulletIndent=4)
    story=[]
    section_names={"PROFESSIONAL SUMMARY","TECHNICAL SKILLS","PROFESSIONAL EXPERIENCE","EDUCATION"}
    nonempty=[p for p in doc.paragraphs if p.text.strip()]
    for i,p in enumerate(nonempty):
        t=p.text.strip()
        if i==0:
            story.append(Paragraph(f"<b>{escape(t)}</b>",ParagraphStyle("Name",parent=center,fontSize=14,leading=16)))
        elif i in (1,2):
            story.append(Paragraph(escape(t),center))
        elif t.upper() in section_names:
            story.append(Paragraph(escape(t.upper()),heading))
        elif p.style and "List Bullet" in p.style.name:
            story.append(Paragraph(escape(t),bullet,bulletText="•"))
        else:
            # Preserve bold runs when possible.
            chunks=[]
            for r in p.runs:
                x=escape(r.text)
                chunks.append(f"<b>{x}</b>" if r.bold else x)
            story.append(Paragraph("".join(chunks) or escape(t),normal))
    pdf=SimpleDocTemplate(str(target),pagesize=LETTER,rightMargin=.5*inch,leftMargin=.5*inch,topMargin=.4*inch,bottomMargin=.4*inch)
    pdf.build(story)
    return str(target) if target.exists() else None
