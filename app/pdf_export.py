from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
from docx import Document


def _find_office() -> str | None:
    """Find a LibreOffice/soffice executable without launching Microsoft Word."""
    candidates = [
        shutil.which("libreoffice"),
        shutil.which("soffice"),
        r"C:\\Program Files\\LibreOffice\\program\\soffice.exe",
        r"C:\\Program Files (x86)\\LibreOffice\\program\\soffice.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def _native_convert(src: Path, target: Path) -> tuple[bool, str]:
    """Render the approved DOCX headlessly. Never use Word COM/UI automation."""
    office = _find_office()
    if not office:
        return False, (
            "LibreOffice/soffice was not found. Install LibreOffice for unattended "
            "DOCX-to-PDF conversion; Microsoft Word COM is intentionally disabled."
        )

    # Use a dedicated temporary LibreOffice profile so stale GUI sessions/profile
    # locks cannot trigger connection/recovery dialogs.
    profile_dir = target.parent / ".lo_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_uri = profile_dir.resolve().as_uri()

    cmd = [
        office,
        "--headless",
        "--nologo",
        "--nodefault",
        "--nolockcheck",
        "--norestore",
        f"-env:UserInstallation={profile_uri}",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(target.parent),
        str(src),
    ]
    try:
        proc = subprocess.run(cmd, check=False, timeout=90, capture_output=True, text=True)
    except Exception as exc:
        return False, f"LibreOffice conversion failed to start: {exc}"

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, f"LibreOffice conversion failed (exit {proc.returncode}): {detail}"

    if target.exists() and target.stat().st_size > 0:
        return True, "ok"
    return False, "LibreOffice completed but PDF was not created"


def convert_docx_to_pdf(docx_path: str) -> str | None:
    """Convert only the approved DOCX; never independently rebuild the PDF."""
    src = Path(docx_path).resolve()
    target = src.with_suffix(".pdf")
    try:
        if target.exists():
            target.unlink()
    except Exception:
        pass
    ok, _ = _native_convert(src, target)
    return str(target) if ok else None


def _docx_signature(docx_path: str) -> dict:
    doc = Document(str(docx_path))
    paragraphs = [re.sub(r"\s+", " ", p.text).strip() for p in doc.paragraphs if p.text.strip()]
    bullets = sum(
        1 for p in doc.paragraphs
        if p.text.strip() and p.style and "List Bullet" in p.style.name
    )
    names = {"PROFESSIONAL SUMMARY", "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE", "EDUCATION"}
    sections = [x.upper() for x in paragraphs if x.upper() in names]
    return {"paragraphs": paragraphs, "bullets": bullets, "sections": sections}


def _pdf_text(pdf_path: str) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        return re.sub(r"\s+", " ", text).strip(), len(reader.pages)
    except Exception:
        return "", 0


def _tokens(text: str) -> list[str]:
    # Token parity tolerates harmless PDF extraction differences in bullets,
    # punctuation, Unicode dashes, and line wrapping without weakening content checks.
    return re.findall(r"[a-z0-9+#./%-]+", text.lower())


def _paragraph_covered(paragraph: str, pdf_tokens: list[str]) -> bool:
    wanted = _tokens(paragraph)
    if not wanted:
        return True
    pdf_set = set(pdf_tokens)
    # Short headings/labels should be exact token subsets. Longer material paragraphs
    # may differ slightly in extraction while still containing the same rendered text.
    ratio = sum(1 for token in wanted if token in pdf_set) / len(wanted)
    threshold = 1.0 if len(wanted) <= 4 else 0.97
    return ratio >= threshold


def validate_docx_pdf_parity(docx_path: str, pdf_path: str | None) -> dict:
    if not pdf_path or not Path(pdf_path).exists() or Path(pdf_path).stat().st_size == 0:
        return {
            "passed": False, "reason": "PDF was not created", "text_coverage": 0,
            "sections_match": False, "page_count": 0,
        }

    sig = _docx_signature(docx_path)
    pdf_text, pages = _pdf_text(pdf_path)
    if not pdf_text:
        return {
            "passed": False, "reason": "PDF text could not be validated",
            "text_coverage": 0, "sections_match": False, "page_count": pages,
        }

    pdf_tokens = _tokens(pdf_text)
    material = [p for p in sig["paragraphs"] if len(p) >= 8]
    matched = sum(1 for p in material if _paragraph_covered(p, pdf_tokens))
    coverage = round(100 * matched / max(1, len(material)), 1)

    pdf_token_set = set(pdf_tokens)
    sections_match = all(set(_tokens(s)).issubset(pdf_token_set) for s in sig["sections"])
    passed = coverage >= 95 and sections_match and pages > 0

    return {
        "passed": passed,
        "reason": None if passed else "DOCX/PDF material text or section mismatch",
        "text_coverage": coverage,
        "sections_match": sections_match,
        "docx_bullet_count": sig["bullets"],
        "sections": sig["sections"],
        "page_count": pages,
        "renderer": "libreoffice_headless",
    }
