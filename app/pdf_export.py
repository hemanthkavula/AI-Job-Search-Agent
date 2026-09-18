from __future__ import annotations
from pathlib import Path
import os, subprocess, shutil, re
from docx import Document

def _native_convert(src: Path, target: Path) -> bool:
    """Use a real Office renderer so the PDF is the exact DOCX layout."""
    if os.name=="nt":
        ps=(
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
    """Convert only from the approved DOCX; never independently rebuild the PDF."""
    src=Path(docx_path).resolve();target=src.with_suffix(".pdf")
    try:
        if target.exists():target.unlink()
    except Exception:pass
    return str(target) if _native_convert(src,target) else None

def _docx_signature(docx_path: str) -> dict:
    doc=Document(str(docx_path))
    paragraphs=[re.sub(r"\s+"," ",p.text).strip() for p in doc.paragraphs if p.text.strip()]
    bullets=sum(1 for p in doc.paragraphs if p.text.strip() and p.style and "List Bullet" in p.style.name)
    names={"PROFESSIONAL SUMMARY","TECHNICAL SKILLS","PROFESSIONAL EXPERIENCE","EDUCATION"}
    sections=[x.upper() for x in paragraphs if x.upper() in names]
    return {"paragraphs":paragraphs,"bullets":bullets,"sections":sections}

def _pdf_text(pdf_path: str) -> tuple[str,int]:
    try:
        from pypdf import PdfReader
        reader=PdfReader(str(pdf_path))
        text="\n".join((p.extract_text() or "") for p in reader.pages)
        return re.sub(r"\s+"," ",text).strip(),len(reader.pages)
    except Exception:return "",0

def validate_docx_pdf_parity(docx_path: str,pdf_path: str|None)->dict:
    if not pdf_path or not Path(pdf_path).exists() or Path(pdf_path).stat().st_size==0:
        return {"passed":False,"reason":"PDF was not created","text_coverage":0,"sections_match":False,"page_count":0}
    sig=_docx_signature(docx_path);pdf_text,pages=_pdf_text(pdf_path)
    if not pdf_text:
        return {"passed":False,"reason":"PDF text could not be validated","text_coverage":0,"sections_match":False,"page_count":pages}
    pdf_norm=pdf_text.lower();material=[p for p in sig["paragraphs"] if len(p)>=8]
    matched=sum(1 for p in material if re.sub(r"\s+"," ",p).lower() in pdf_norm)
    coverage=round(100*matched/max(1,len(material)),1)
    sections_match=all(s.lower() in pdf_norm for s in sig["sections"])
    passed=coverage>=95 and sections_match and pages>0
    return {"passed":passed,"reason":None if passed else "DOCX/PDF material text or section mismatch",
            "text_coverage":coverage,"sections_match":sections_match,"docx_bullet_count":sig["bullets"],
            "sections":sig["sections"],"page_count":pages}
