from __future__ import annotations
from pathlib import Path
import shutil, subprocess, sys

def convert_docx_to_pdf(docx_path: str) -> str | None:
    """Convert generated DOCX to PDF. Uses Word on Windows when docx2pdf is available,
    otherwise LibreOffice when installed. Returns None if no converter is available."""
    src=Path(docx_path).resolve(); target=src.with_suffix(".pdf")
    try:
        if sys.platform.startswith("win"):
            from docx2pdf import convert
            convert(str(src),str(target))
            if target.exists(): return str(target)
    except Exception:
        pass
    soffice=shutil.which("libreoffice") or shutil.which("soffice")
    if soffice:
        subprocess.run([soffice,"--headless","--convert-to","pdf","--outdir",str(src.parent),str(src)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if target.exists(): return str(target)
    return None
