from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import time

from docx import Document

from app.resume_pagination import enforce_experience_start_rule, validate_experience_start_rule


REQUIRED_PRODUCTION_PAGES = 2
MIN_PAGE_TEXT_BALANCE = 0.50
REQUIRED_PDF_FONT_FAMILY = "Calibri"
ALLOWED_METRIC_FALLBACK_FONT = "Carlito"
DISALLOWED_SUBSTITUTE_FONTS = ("dejavu", "liberation")
# Employer placement is intentionally NOT hardcoded. An employer may begin on the
# current page when its company/header, title/date, responsibilities label, and
# complete first bullet fit there. Otherwise Word/LibreOffice moves that start block
# to the next page. Only the high-level two-page section flow remains fixed.
EXPECTED_PAGE_PLACEMENT = {
    "PROFESSIONAL SUMMARY": 0,
    "TECHNICAL SKILLS": 0,
    "PROFESSIONAL EXPERIENCE": 0,
    "EDUCATION": 1,
}


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
    """Apply pagination policy, convert DOCX to PDF, and return diagnostics."""
    src = Path(docx_path).resolve()
    max_attempts = max(1, attempts)
    result = {
        "pdf_path": None,
        "attempts": 0,
        "reason": None,
        "renderer": "libreoffice_headless",
        "source_artifact": "docx",
        "experience_start_pagination": None,
    }
    if not src.exists() or src.stat().st_size == 0:
        result["reason"] = f"DOCX missing or empty: {src}"
        print(f"PDF conversion skipped | {result['reason']}", flush=True)
        return result

    pagination = enforce_experience_start_rule(src)
    result["experience_start_pagination"] = pagination
    if not pagination.get("passed"):
        result["reason"] = "Resume pagination policy failed: " + "; ".join(
            pagination.get("reasons") or ["unknown pagination error"]
        )
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


def _pdf_font_names(pdf_path: str) -> list[str]:
    """Return normalized BaseFont names used by the rendered PDF."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        names = set()
        for page in reader.pages:
            resources = page.get("/Resources") or {}
            fonts = resources.get("/Font") or {}
            try:
                fonts = fonts.get_object()
            except Exception:
                pass
            for ref in getattr(fonts, "values", lambda: [])():
                try:
                    font = ref.get_object()
                except Exception:
                    font = ref
                name = str(font.get("/BaseFont") or "").lstrip("/")
                if "+" in name and len(name.split("+", 1)[0]) == 6:
                    name = name.split("+", 1)[1]
                if name:
                    names.add(name)
        return sorted(names)
    except Exception:
        return []


def _pdf_font_contract(pdf_path: str) -> tuple[bool, list[str], list[str], bool]:
    names = _pdf_font_names(pdf_path)
    lowered = [name.casefold() for name in names]
    has_calibri = any(REQUIRED_PDF_FONT_FAMILY.casefold() in name for name in lowered)
    has_metric_fallback = any(ALLOWED_METRIC_FALLBACK_FONT.casefold() in name for name in lowered)
    substitutions = [
        original
        for original, low in zip(names, lowered)
        if any(bad in low for bad in DISALLOWED_SUBSTITUTE_FONTS)
    ]
    fallback_used = has_metric_fallback and not has_calibri
    return (has_calibri or has_metric_fallback) and not substitutions, names, substitutions, fallback_used


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


def _page_index(page_texts: list[str], needle: str) -> int | None:
    wanted = re.sub(r"\s+", " ", needle).strip().casefold()
    for index, page in enumerate(page_texts):
        normalized = re.sub(r"\s+", " ", page).strip().casefold()
        if wanted in normalized:
            return index
    return None


def _page_text_balance(page_texts: list[str]) -> tuple[float, list[int]]:
    counts = [len(re.sub(r"\s+", "", page or "")) for page in page_texts]
    if not counts or max(counts) == 0:
        return 0.0, counts
    return round(min(counts) / max(counts), 3), counts


def validate_docx_pdf_parity(docx_path: str, pdf_path: str | None) -> dict:
    """Validate DOCX→PDF integrity and the hard production layout contract.

    Production remains a compact two-page resume. Employer placement is dynamic:
    an employer may start on the current page only when its header, title/date,
    responsibilities label, and complete first bullet fit together. Later bullets
    may continue naturally onto following pages.
    """
    pagination = validate_experience_start_rule(docx_path)
    if not pdf_path or not Path(pdf_path).exists() or Path(pdf_path).stat().st_size == 0:
        return {
            "passed": False,
            "reason": "PDF was not created",
            "text_coverage": 0,
            "sections_match": False,
            "page_count": 0,
            "required_page_count": REQUIRED_PRODUCTION_PAGES,
            "page_count_match": False,
            "page_flow_match": False,
            "page_text_balance": 0.0,
            "page_text_counts": [],
            "environment_footers_match": False,
            "experience_start_pagination": pagination,
            "pagination_policy": "two_page_first_bullet_experience_start_contract",
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
            "required_page_count": REQUIRED_PRODUCTION_PAGES,
            "page_count_match": pages == REQUIRED_PRODUCTION_PAGES,
            "page_flow_match": False,
            "page_text_balance": 0.0,
            "page_text_counts": [],
            "environment_footers_match": False,
            "experience_start_pagination": pagination,
            "pagination_policy": "two_page_first_bullet_experience_start_contract",
        }

    pdf_tokens = _tokens(pdf_text)
    material = [paragraph for paragraph in sig["paragraphs"] if len(paragraph) >= 8]
    matched = sum(1 for paragraph in material if _paragraph_covered(paragraph, pdf_tokens))
    coverage = round(100 * matched / max(1, len(material)), 1)

    pdf_token_set = set(pdf_tokens)
    sections_match = all(
        set(_tokens(section)).issubset(pdf_token_set) for section in sig["sections"]
    )

    page_count_match = pages == REQUIRED_PRODUCTION_PAGES
    placements = {
        label: _page_index(page_texts, label)
        for label in EXPECTED_PAGE_PLACEMENT
    }
    page_flow_match = page_count_match and all(
        placements.get(label) == expected_page
        for label, expected_page in EXPECTED_PAGE_PLACEMENT.items()
    )

    balance, page_text_counts = _page_text_balance(page_texts)
    page_balance_match = (
        page_count_match
        and len(page_text_counts) == REQUIRED_PRODUCTION_PAGES
        and balance >= MIN_PAGE_TEXT_BALANCE
    )

    environment_footer_count = pdf_text.casefold().count("environment:")
    environment_footers_match = environment_footer_count >= 3
    skills_footer_removed = "skills:" not in pdf_text.casefold()
    pdf_font_match, pdf_fonts, substituted_fonts, pdf_font_fallback_used = _pdf_font_contract(pdf_path)

    failures = []
    if not pagination.get("passed"):
        failures.append(
            "employer start pagination rule failed: "
            + "; ".join(pagination.get("reasons") or ["unknown pagination error"])
        )
    if coverage < 95:
        failures.append("DOCX/PDF material text mismatch")
    if not sections_match:
        failures.append("section mismatch")
    if not page_count_match:
        failures.append(
            f"production resume must be exactly {REQUIRED_PRODUCTION_PAGES} pages; got {pages}"
        )
    if page_count_match and not page_flow_match:
        failures.append("master-like section page flow mismatch")
    if page_count_match and not page_balance_match:
        failures.append(
            f"page content is too unbalanced/sparse (balance={balance}, minimum={MIN_PAGE_TEXT_BALANCE})"
        )
    if not environment_footers_match:
        failures.append("expected compact Environment footers were not found for all employers")
    if not skills_footer_removed:
        failures.append("legacy Skills employer footer is still present")
    if not pdf_font_match:
        if substituted_fonts:
            failures.append(
                "PDF font substitution detected; required Calibri but found substitute font(s): "
                + ", ".join(substituted_fonts)
            )
        else:
            failures.append(
                "PDF does not contain Calibri or the approved Carlito metric-compatible fallback; renderer fonts="
                + (", ".join(pdf_fonts) if pdf_fonts else "unknown")
            )

    passed = not failures
    return {
        "passed": passed,
        "reason": None if passed else "; ".join(failures),
        "text_coverage": coverage,
        "sections_match": sections_match,
        "sections": sig["sections"],
        "page_count": pages,
        "required_page_count": REQUIRED_PRODUCTION_PAGES,
        "page_count_match": page_count_match,
        "page_flow_match": page_flow_match,
        "expected_page_placement": EXPECTED_PAGE_PLACEMENT,
        "actual_page_placement": placements,
        "page_text_balance": balance,
        "page_text_counts": page_text_counts,
        "minimum_page_text_balance": MIN_PAGE_TEXT_BALANCE,
        "page_balance_match": page_balance_match,
        "environment_footer_count": environment_footer_count,
        "environment_footers_match": environment_footers_match,
        "skills_footer_removed": skills_footer_removed,
        "required_pdf_font_family": REQUIRED_PDF_FONT_FAMILY,
        "allowed_metric_fallback_font": ALLOWED_METRIC_FALLBACK_FONT,
        "pdf_fonts": pdf_fonts,
        "pdf_font_match": pdf_font_match,
        "pdf_font_fallback_used": pdf_font_fallback_used,
        "substituted_fonts": substituted_fonts,
        "experience_start_pagination": pagination,
        "pagination_policy": "two_page_first_bullet_experience_start_contract",
        "renderer": "libreoffice_headless",
        "source_artifact": "docx",
    }
