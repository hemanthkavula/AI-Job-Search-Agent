from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import time

from docx import Document


def _find_office() -> str | None:
    """Find a LibreOffice/soffice executable without launching Microsoft Word."""
    candidates = [
        shutil.which("libreoffice"),
        shutil.which("soffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def _native_convert(src: Path, target: Path) -> tuple[bool, str]:
    """Render one approved DOCX headlessly using an isolated LibreOffice profile."""
    office = _find_office()
    if not office:
        return False, (
            "LibreOffice/soffice was not found. Install LibreOffice for unattended "
            "DOCX-to-PDF conversion; Microsoft Word COM is intentionally disabled."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    profile_dir = Path(tempfile.mkdtemp(prefix="ai_job_resume_lo_"))
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
    env = dict(os.environ)
    env["SAL_DISABLE_SYNCHRONOUS_PRINTER_DETECTION"] = "1"
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            timeout=90,
            capture_output=True,
            text=True,
            env=env,
        )
        detail = "\n".join(
            x.strip() for x in (proc.stdout, proc.stderr) if x and x.strip()
        )
        if proc.returncode != 0:
            return False, (
                f"LibreOffice conversion failed (exit {proc.returncode}): "
                f"{detail or 'no diagnostic output'}"
            )

        for _ in range(20):
            if target.exists() and target.stat().st_size > 0:
                return True, "ok"
            time.sleep(0.25)
        return False, (
            "LibreOffice exited successfully but PDF was not created"
            + (f": {detail}" if detail else "")
        )
    except subprocess.TimeoutExpired:
        return False, "LibreOffice conversion timed out after 90 seconds"
    except Exception as exc:
        return False, f"LibreOffice conversion failed to start: {exc}"
    finally:
        def _onerror(func, path, exc_info):
            try:
                os.chmod(path, 0o700)
                func(path)
            except OSError:
                pass

        shutil.rmtree(profile_dir, onerror=_onerror)


def _conversion_attempt(src: Path, target: Path) -> tuple[bool, str]:
    try:
        if target.exists():
            target.unlink()
    except OSError as exc:
        return False, f"Existing PDF could not be replaced: {exc}"
    return _native_convert(src, target)


def convert_docx_to_pdf_detailed(docx_path: str, attempts: int = 2) -> dict:
    """Convert the generated Word document to PDF and return conversion diagnostics."""
    src = Path(docx_path).resolve()
    max_attempts = max(1, attempts)
    result = {
        "pdf_path": None,
        "attempts": 0,
        "reason": None,
        "renderer": "libreoffice_headless",
        "source_artifact": "docx",
    }
    if not src.exists() or src.stat().st_size == 0:
        result["reason"] = f"DOCX missing or empty: {src}"
        print(f"PDF conversion skipped | {result['reason']}", flush=True)
        return result

    target = src.with_suffix(".pdf")
    for attempt in range(1, max_attempts + 1):
        result["attempts"] = attempt
        ok, reason = _conversion_attempt(src, target)
        result["reason"] = None if ok else reason
        if ok:
            result["pdf_path"] = str(target)
            if attempt > 1:
                print(f"PDF conversion recovered on attempt {attempt}", flush=True)
            return result
        print(f"PDF conversion attempt {attempt}/{max_attempts} failed | {reason}", flush=True)
        if attempt < max_attempts:
            time.sleep(1.0)

    print(f"PDF conversion exhausted retries | {result['reason']}", flush=True)
    return result


def convert_docx_to_pdf(docx_path: str, attempts: int = 2) -> str | None:
    """Backward-compatible path-only wrapper around detailed conversion."""
    return convert_docx_to_pdf_detailed(docx_path, attempts=attempts)["pdf_path"]


def _docx_signature(docx_path: str) -> dict:
    doc = Document(str(docx_path))
    paragraphs = [
        re.sub(r"\s+", " ", p.text).strip()
        for p in doc.paragraphs
        if p.text.strip()
    ]
    names = {
        "PROFESSIONAL SUMMARY",
        "TECHNICAL SKILLS",
        "PROFESSIONAL EXPERIENCE",
        "EDUCATION",
    }
    sections = [x.upper() for x in paragraphs if x.upper() in names]
    return {"paragraphs": paragraphs, "sections": sections}


def _pdf_pages_text(pdf_path: str) -> list[str]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        return [
            re.sub(r"\s+", " ", (page.extract_text() or "")).strip()
            for page in reader.pages
        ]
    except Exception:
        return []


def _tokens(text: str) -> list[str]:
    normalized = re.sub(r"(?<=[a-z0-9])-\s+(?=[a-z0-9])", "-", text.lower())
    return re.findall(r"[a-z0-9+#./%-]+", normalized)


def _paragraph_covered(paragraph: str, pdf_tokens: list[str]) -> bool:
    wanted = _tokens(paragraph)
    if not wanted:
        return True
    pdf_set = set(pdf_tokens)
    ratio = sum(1 for token in wanted if token in pdf_set) / len(wanted)
    threshold = 1.0 if len(wanted) <= 4 else 0.97
    return ratio >= threshold


def validate_docx_pdf_parity(docx_path: str, pdf_path: str | None) -> dict:
    """Validate DOCX→PDF integrity without imposing a page-count requirement.

    The user's master resume controls visual formatting (font, color, margins,
    paragraph spacing, section structure). Pagination is natural: 2, 3, or more
    pages are all acceptable when the tailored content needs them.
    """
    if not pdf_path or not Path(pdf_path).exists() or Path(pdf_path).stat().st_size == 0:
        return {
            "passed": False,
            "reason": "PDF was not created",
            "text_coverage": 0,
            "sections_match": False,
            "page_count": 0,
            "required_page_count": None,
            "page_count_match": True,
            "page_flow_match": True,
            "pagination_policy": "natural_non_blocking",
        }

    sig = _docx_signature(docx_path)
    page_texts = _pdf_pages_text(pdf_path)
    pages = len(page_texts)
    pdf_text = " ".join(page_texts).strip()
    if not pdf_text:
        return {
            "passed": False,
            "reason": "PDF text could not be validated",
            "text_coverage": 0,
            "sections_match": False,
            "page_count": pages,
            "required_page_count": None,
            "page_count_match": True,
            "page_flow_match": True,
            "pagination_policy": "natural_non_blocking",
        }

    pdf_tokens = _tokens(pdf_text)
    material = [paragraph for paragraph in sig["paragraphs"] if len(paragraph) >= 8]
    matched = sum(1 for paragraph in material if _paragraph_covered(paragraph, pdf_tokens))
    coverage = round(100 * matched / max(1, len(material)), 1)

    pdf_token_set = set(pdf_tokens)
    sections_match = all(
        set(_tokens(section)).issubset(pdf_token_set) for section in sig["sections"]
    )

    failures = []
    if coverage < 95:
        failures.append("DOCX/PDF material text mismatch")
    if not sections_match:
        failures.append("section mismatch")

    passed = not failures
    return {
        "passed": passed,
        "reason": None if passed else "; ".join(failures),
        "text_coverage": coverage,
        "sections_match": sections_match,
        "sections": sig["sections"],
        "page_count": pages,
        "required_page_count": None,
        "page_count_match": True,
        "page_flow_match": True,
        "pagination_policy": "natural_non_blocking",
        "renderer": "libreoffice_headless",
        "source_artifact": "docx",
    }
