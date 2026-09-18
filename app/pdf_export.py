from __future__ import annotations
from pathlib import Path
import os, subprocess, shutil, re
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


def _docx_signature(docx_path: str) -> dict:
    """Extract deterministic text/structure signals from the generated DOCX."""
    doc=Document(str(docx_path))
    paragraphs=[re.sub(r"\s+"," ",p.text).strip() for p in doc.paragraphs if p.text.strip()]
    bullets=sum(1 for p in doc.paragraphs if p.text.strip() and p.style and "List Bullet" in p.style.name)
    sections=[x.upper() for x in paragraphs if x.upper() in {"PROFESSIONAL SUMMARY","TECHNICAL SKILLS","PROFESSIONAL EXPERIENCE","EDUCATION"}]
    return {"paragraphs":paragraphs,"bullets":bullets,"sections":sections}

def _pdf_text(pdf_path: str) -> tuple[str,int]:
    """Use a lightweight PDF parser when available; never OCR resume artifacts."""
    try:
        from pypdf import PdfReader
        reader=PdfReader(str(pdf_path))
        text="\n".join((p.extract_text() or "") for p in reader.pages)
        return re.sub(r"\s+"," ",text).strip(),len(reader.pages)
    except Exception:
        return "",0

def validate_docx_pdf_parity(docx_path: str, pdf_path: str | None) -> dict:
    """Require material text/section parity before an artifact can be submitted."""
    if not pdf_path or not Path(pdf_path).exists() or Path(pdf_path).stat().st_size==0:
        return {"passed":False,"reason":"PDF was not created","text_coverage":0,"sections_match":False,"page_count":0}
    sig=_docx_signature(docx_path);pdf_text,pages=_pdf_text(pdf_path)
    if not pdf_text:
        return {"passed":False,"reason":"PDF text could not be validated","text_coverage":0,"sections_match":False,"page_count":pages}
    pdf_norm=pdf_text.lower()
    # Paragraph-level containment tolerates normal line wrapping while catching
    # missing bullets/sections caused by renderer failures or clipping.
    material=[p for p in sig["paragraphs"] if len(p)>=8]
    matched=sum(1 for p in material if re.sub(r"\s+"," ",p).lower() in pdf_norm)
    coverage=round(100*matched/max(1,len(material)),1)
    sections=[s for s in sig["sections"] if s.lower() in pdf_norm]
    sections_match=len(sections)==len(sig["sections"])
    passed=coverage>=95 and sections_match and pages>0
    return {"passed":passed,"reason":None if passed else "DOCX/PDF material text or section mismatch",
            "text_coverage":coverage,"sections_match":sections_match,"docx_bullet_count":sig["bullets"],
            "sections":sig["sections"],"page_count":pages}
