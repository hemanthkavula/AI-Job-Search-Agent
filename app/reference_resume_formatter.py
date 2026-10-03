from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from app.resume_generator import ROOT, clean_company_name, safe_name


MASTER_BULLET_COUNTS = {
    "Fidelity Investments": 10,
    "Cigna Healthcare": 8,
    "Target Corporation": 8,
}

# These are fallbacks for the current uploaded master. Whenever a value is
# present under candidate_profile.master_resume_reference.style it wins. That
# makes the master profile the visual source of truth instead of scattering
# resume styling constants throughout the renderer.
DEFAULT_MASTER_STYLE = {
    "font": "Calibri",
    "name_pt": 18,
    "headline_pt": 13,
    "contact_pt": 11,
    "section_heading_pt": 12,
    "summary_pt": 11,
    "body_pt": 10,
    "company_pt": 12,
    "job_title_pt": 11,
    "accent_hex": "1F4E79",
    "gray_hex": "595959",
    "link_hex": "0563C1",
    "top_margin_in": 0.55,
    "bottom_margin_in": 0.42,
    "left_margin_in": 0.50,
    "right_margin_in": 0.50,
    "right_tab_in": 7.45,
    "bullet_left_indent_in": 0.50,
    "bullet_hanging_indent_in": -0.18,
    "section_before_pt": 10,
    "section_after_pt": 5,
    "summary_first_after_pt": 7,
    "summary_last_after_pt": 3,
    "summary_line_spacing": 1.05,
    "bullet_after_pt": 3,
    "environment_after_pt": 8,
    "selective_phrase_bold": True,
    "roles_and_responsibilities_label": True,
    "environment_line": True,
    "right_aligned_dates": True,
    "two_summary_paragraphs": True,
}


def _master_style(profile):
    style = dict(DEFAULT_MASTER_STYLE)
    configured = (
        profile.get("master_resume_reference", {})
        .get("style", {})
    )
    if isinstance(configured, dict):
        style.update({k: v for k, v in configured.items() if v is not None})
    return style


def _rgb(hex_value):
    value = str(hex_value or "000000").strip().lstrip("#")
    if len(value) != 6:
        value = "000000"
    return RGBColor.from_string(value.upper())


def _run(r, style, size=None, bold=False, color=None, underline=False):
    r.font.name = style["font"]
    r.font.size = Pt(size if size is not None else style["body_pt"])
    r.bold = bold
    r.underline = underline
    if color:
        r.font.color.rgb = color
    return r


def _compact(p, before=0, after=0, line=1.0):
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = line


def _section(doc, text, style, after=None):
    accent = _rgb(style["accent_hex"])
    p = doc.add_paragraph()
    _compact(
        p,
        style["section_before_pt"],
        style["section_after_pt"] if after is None else after,
    )
    p.paragraph_format.keep_with_next = True
    _run(p.add_run(text), style, style["section_heading_pt"], True, accent)

    p_pr = p._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), str(style["accent_hex"]).lstrip("#").upper())
    p_bdr.append(bottom)
    p_pr.append(p_bdr)
    return p


def _emphasis_runs(p, text, phrases, style, size=None, color=None):
    text = str(text or "")
    candidates = [str(x).strip() for x in (phrases or []) if str(x).strip()]
    seen = set()
    selected = []
    for phrase in sorted(candidates, key=len, reverse=True):
        key = phrase.casefold()
        if key not in seen and key in text.casefold():
            seen.add(key)
            selected.append(phrase)

    if not selected:
        _run(p.add_run(text), style, size, False, color)
        return

    pattern = re.compile("(" + "|".join(re.escape(x) for x in selected) + ")", re.I)
    lookup = {x.casefold() for x in selected}
    for part in pattern.split(text):
        if part:
            _run(p.add_run(part), style, size, part.casefold() in lookup, color)


def _summary_parts(text):
    text = str(text or "").strip()
    parts = [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()]
    if len(parts) >= 2:
        return parts[:2]

    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
    if len(sentences) >= 4:
        return [" ".join(sentences[:2]), " ".join(sentences[2:])]
    if len(sentences) == 3:
        return [sentences[0], " ".join(sentences[1:])]
    return [text] if text else []


def _all_skill_terms(generated):
    out = []
    for vals in (generated.get("skills") or {}).values():
        out.extend(str(x) for x in (vals or []))
    return list(dict.fromkeys(out))


def _metric_terms(text):
    patterns = [
        r"~?\d+(?:\.\d+)?\s*[–-]\s*\d+(?:\.\d+)?\s*(?:GB/day|GB|TB|%|M|million)?",
        r"~?\d+(?:\.\d+)?\s*(?:GB/day|GB|TB|%|M|million)",
    ]
    hits = []
    for pattern in patterns:
        hits.extend(m.group(0) for m in re.finditer(pattern, text, re.I))
    return list(dict.fromkeys(hits))


def _fallback_emphasis(text, generated, max_terms=2):
    hits = []
    for term in sorted(_all_skill_terms(generated), key=len, reverse=True):
        if len(term) >= 3 and re.search(
            r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])",
            text,
            re.I,
        ):
            hits.append(term)
    hits = _metric_terms(text) + hits
    return list(dict.fromkeys(hits))[:max_terms]


def _company_header(doc, base, style):
    accent = _rgb(style["accent_hex"])
    gray = _rgb(style["gray_hex"])

    p = doc.add_paragraph()
    _compact(p, 7, 0)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.tab_stops.add_tab_stop(
        Inches(style["right_tab_in"]), WD_TAB_ALIGNMENT.RIGHT
    )
    _run(p.add_run(base["company"]), style, style["company_pt"], True)
    _run(p.add_run(" | " + base.get("location", "")), style, style["body_pt"])
    _run(p.add_run("\t" + base["dates"]), style, style["body_pt"], False, gray)

    title = doc.add_paragraph()
    _compact(title, 0, 1)
    title.paragraph_format.keep_with_next = True
    _run(title.add_run(base["title"]), style, style["job_title_pt"], True, accent)

    roles = doc.add_paragraph()
    _compact(roles, 0, 1)
    roles.paragraph_format.keep_with_next = True
    _run(roles.add_run("Roles & Responsibilities:"), style, style["body_pt"], True)
    return p, title, roles


def canonical_resume_title(title):
    raw = re.sub(r"\s+", " ", str(title or "")).strip()
    m = re.search(
        r"(?i)\b(?:(principal|staff|lead|senior|sr\.?|junior|jr\.?)\s+)?data\s+engineer(?:ing)?\b",
        raw,
    )
    if m:
        level = (m.group(1) or "").lower().rstrip(".")
        level = {"sr": "Senior", "jr": "Junior"}.get(level, level.title())
        core = "Data Engineering" if re.search(r"(?i)data\s+engineering", m.group(0)) else "Data Engineer"
        return f"{level} {core}".strip()

    cleaned = re.sub(
        r"(?i)^\s*(?:immediate interviews?|urgent(?: hiring)?|hiring now)\s*[-:|]\s*",
        "",
        raw,
    )
    cleaned = re.split(
        r"\s+(?:[-|/]\s*)(?=(?:airflow|dbt|kubernetes|openshift|aws|azure|gcp|snowflake|databricks|hybrid|remote|onsite|on-site)\b)",
        cleaned,
        1,
        flags=re.I,
    )[0]
    return cleaned.strip(" -|:/") or "Senior Data Engineer"


def _expected_bullet_counts(profile):
    configured = profile.get("master_resume_reference", {}).get("bullet_counts", {})
    return configured or MASTER_BULLET_COUNTS


def validate_master_format_contract(path, profile):
    """Validate that a generated DOCX still follows the uploaded master visual contract.

    This is deliberately a formatting/structure gate, not an ATS-content gate. It
    catches accidental renderer drift before the document can move downstream.
    """
    style = _master_style(profile)
    expected_counts = _expected_bullet_counts(profile)
    doc = Document(path)
    paras = doc.paragraphs
    reasons = []

    normal = doc.styles["Normal"]
    if normal.font.name != style["font"]:
        reasons.append(f"normal_font={normal.font.name!r}")
    if normal.font.size != Pt(style["body_pt"]):
        reasons.append(f"normal_size={normal.font.size}")

    section = doc.sections[0]
    margin_checks = {
        "top_margin_in": section.top_margin.inches,
        "bottom_margin_in": section.bottom_margin.inches,
        "left_margin_in": section.left_margin.inches,
        "right_margin_in": section.right_margin.inches,
    }
    for key, actual in margin_checks.items():
        if abs(actual - float(style[key])) > 0.015:
            reasons.append(f"{key}={actual:.3f}")

    if len(paras) < 3:
        reasons.append("missing_header_paragraphs")
    else:
        if paras[0].alignment != WD_ALIGN_PARAGRAPH.CENTER:
            reasons.append("name_not_centered")
        if not paras[0].runs or paras[0].runs[0].font.size != Pt(style["name_pt"]):
            reasons.append("name_size_mismatch")
        if not paras[1].runs or paras[1].runs[0].font.size != Pt(style["headline_pt"]):
            reasons.append("headline_size_mismatch")
        if not paras[2].runs or any(
            run.font.size != Pt(style["contact_pt"]) for run in paras[2].runs if run.text
        ):
            reasons.append("contact_size_mismatch")

    expected_sections = [
        "PROFESSIONAL SUMMARY",
        "TECHNICAL SKILLS",
        "PROFESSIONAL EXPERIENCE",
        "EDUCATION",
    ]
    accent_hex = str(style["accent_hex"]).lstrip("#").upper()
    for label in expected_sections:
        matches = [p for p in paras if p.text == label]
        if len(matches) != 1:
            reasons.append(f"section_{label}_count={len(matches)}")
            continue
        run = matches[0].runs[0] if matches[0].runs else None
        if not run or run.font.size != Pt(style["section_heading_pt"]) or not run.bold:
            reasons.append(f"section_{label}_typography")
        elif not run.font.color.rgb or str(run.font.color.rgb).upper() != accent_hex:
            reasons.append(f"section_{label}_color")

    try:
        summary_heading = next(p for p in paras if p.text == "PROFESSIONAL SUMMARY")
        skills_heading = next(p for p in paras if p.text == "TECHNICAL SKILLS")
        start = paras.index(summary_heading) + 1
        end = paras.index(skills_heading)
        summary_paras = [p for p in paras[start:end] if p.text.strip()]
        if style.get("two_summary_paragraphs") and len(summary_paras) != 2:
            reasons.append(f"summary_paragraphs={len(summary_paras)}")
        for p in summary_paras:
            if any(run.font.size != Pt(style["summary_pt"]) for run in p.runs if run.text):
                reasons.append("summary_size_mismatch")
                break
        if style.get("selective_phrase_bold") and not any(
            run.bold for p in summary_paras for run in p.runs if run.text.strip()
        ):
            reasons.append("summary_missing_selective_bold")
    except StopIteration:
        pass

    roles_count = sum(p.text == "Roles & Responsibilities:" for p in paras)
    environment_count = sum(p.text.startswith("Environment: ") for p in paras)
    if style.get("roles_and_responsibilities_label") and roles_count != len(expected_counts):
        reasons.append(f"roles_labels={roles_count}")
    if style.get("environment_line") and environment_count != len(expected_counts):
        reasons.append(f"environment_lines={environment_count}")

    current = None
    counts = {company: 0 for company in expected_counts}
    fidelity_bullets = []
    skill_labels = set((profile.get("skill_categories") or {}).keys())
    for p in paras:
        for company in expected_counts:
            if p.text.startswith(company):
                current = company
                break
        else:
            if current and p.style and "List Bullet" in p.style.name:
                counts[current] += 1
                if p.paragraph_format.left_indent != Inches(style["bullet_left_indent_in"]):
                    reasons.append(f"{current}_bullet_left_indent")
                if p.paragraph_format.first_line_indent != Inches(style["bullet_hanging_indent_in"]):
                    reasons.append(f"{current}_bullet_hanging_indent")
                if any(run.font.size != Pt(style["body_pt"]) for run in p.runs if run.text):
                    reasons.append(f"{current}_bullet_size")
                if current == "Fidelity Investments":
                    fidelity_bullets.append(p)

        if ": " in p.text:
            label = p.text.split(": ", 1)[0]
            if label in skill_labels and (not p.runs or not p.runs[0].bold):
                reasons.append(f"skill_label_not_bold={label}")

    if counts != expected_counts:
        reasons.append(f"bullet_counts={counts}")
    if len(fidelity_bullets) >= 9 and fidelity_bullets[8].paragraph_format.page_break_before is not True:
        reasons.append("fidelity_page2_break_missing")

    for p in paras:
        if p.text.startswith("Environment: ") and (not p.runs or not p.runs[0].bold):
            reasons.append("environment_label_not_bold")
            break

    return {
        "passed": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "layout_version": profile.get("master_resume_reference", {}).get("layout_version"),
    }


def render_llm_resume(job, profile, generated, output_dir="generated/resumes"):
    """Render every base/JD-specific resume in the uploaded 2026-10-03 master style."""
    style = _master_style(profile)
    accent = _rgb(style["accent_hex"])
    gray = _rgb(style["gray_hex"])
    link = _rgb(style["link_hex"])

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(style["top_margin_in"])
    section.bottom_margin = Inches(style["bottom_margin_in"])
    section.left_margin = Inches(style["left_margin_in"])
    section.right_margin = Inches(style["right_margin_in"])

    doc.styles["Normal"].font.name = style["font"]
    doc.styles["Normal"].font.size = Pt(style["body_pt"])
    doc.styles["Normal"].paragraph_format.space_after = Pt(0)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _compact(p, 0, 2.5)
    _run(p.add_run(profile["name"]), style, style["name_pt"], True, accent)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _compact(p, 0, 3)
    _run(
        p.add_run(canonical_resume_title(job.title or profile.get("headline", "Senior Data Engineer"))),
        style,
        style["headline_pt"],
        False,
        accent,
    )

    contact = profile.get("contact", {})
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _compact(p, 0, 7)
    values = [x for x in [contact.get("phone"), contact.get("email"), contact.get("linkedin")] if x]
    for index, value in enumerate(values):
        if index:
            _run(p.add_run(" | "), style, style["contact_pt"])
        is_link = "@" in value or "linkedin" in value.lower()
        _run(
            p.add_run(value),
            style,
            style["contact_pt"],
            False,
            link if is_link else None,
            is_link,
        )

    _section(doc, "PROFESSIONAL SUMMARY", style, 4)
    summary_emphasis = generated.get("summary_emphasis") or profile.get("summary_emphasis") or []
    parts = _summary_parts(generated.get("summary", ""))
    for index, part in enumerate(parts):
        p = doc.add_paragraph()
        after = style["summary_first_after_pt"] if index == 0 and len(parts) > 1 else style["summary_last_after_pt"]
        _compact(p, 0, after, style["summary_line_spacing"])
        phrases = [x for x in summary_emphasis if str(x).casefold() in part.casefold()]
        if not phrases:
            phrases = _fallback_emphasis(part, generated, 5)
        _emphasis_runs(p, part, phrases, style, style["summary_pt"])

    _section(doc, "TECHNICAL SKILLS", style, 7)
    for label, values in (generated.get("skills") or {}).items():
        p = doc.add_paragraph()
        _compact(p, 0, 0.2, 1.0)
        _run(p.add_run(str(label) + ": "), style, style["body_pt"], True)
        _run(p.add_run(", ".join(str(v) for v in values)), style, style["body_pt"])

    _section(doc, "PROFESSIONAL EXPERIENCE", style, 4)
    expected = {x["company"]: x for x in profile["experience"]}
    bullet_counts = _expected_bullet_counts(profile)
    for item in generated.get("experience", []):
        base = expected.get(item.get("company"))
        if not base:
            continue
        _, _, roles_p = _company_header(doc, base, style)
        first_bullet = None
        emphasis_rows = item.get("bullet_emphasis") or base.get("bullet_emphasis") or []
        limit = bullet_counts.get(base["company"], 8)
        for index, line in enumerate((item.get("bullets") or [])[:limit]):
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.left_indent = Inches(style["bullet_left_indent_in"])
            p.paragraph_format.first_line_indent = Inches(style["bullet_hanging_indent_in"])
            p.paragraph_format.keep_together = True
            _compact(p, 0, style["bullet_after_pt"], 1.0)

            # The uploaded master intentionally continues Fidelity bullets 9-10
            # on page two, so preserve that exact visual break for every resume.
            if base["company"] == "Fidelity Investments" and index == 8:
                p.paragraph_format.page_break_before = True

            phrases = (
                emphasis_rows[index]
                if index < len(emphasis_rows) and isinstance(emphasis_rows[index], list)
                else []
            )
            if not phrases:
                phrases = _fallback_emphasis(str(line), generated, 2)
            _emphasis_runs(p, str(line).strip(), phrases, style, style["body_pt"])
            if first_bullet is None:
                first_bullet = p

        env = doc.add_paragraph()
        _compact(env, 1, style["environment_after_pt"])
        _run(env.add_run("Environment: "), style, style["body_pt"], True)
        _run(env.add_run(base.get("environment", "")), style, style["body_pt"])
        if first_bullet is None:
            roles_p.paragraph_format.keep_with_next = False

    _section(doc, "EDUCATION", style, 4)
    for education in profile["education"]:
        p = doc.add_paragraph()
        _compact(p, 0, 1)
        p.paragraph_format.keep_with_next = True
        _run(p.add_run(education["degree"]), style, style["job_title_pt"], True)

        p = doc.add_paragraph()
        _compact(p, 0, 0)
        p.paragraph_format.tab_stops.add_tab_stop(
            Inches(style["right_tab_in"]), WD_TAB_ALIGNMENT.RIGHT
        )
        _run(
            p.add_run(f"{education['school']} | {education['location']}"),
            style,
            style["body_pt"],
        )
        _run(
            p.add_run("\t" + f"{education['start']} – {education['end']}"),
            style,
            style["body_pt"],
            False,
            gray,
        )

    root = ROOT / output_dir
    root.mkdir(parents=True, exist_ok=True)
    pattern = profile.get("output", {}).get(
        "resume_filename_pattern", "Hemanth_Kavula_{Company}_{JobTitle}"
    )
    clean_title = canonical_resume_title(job.title)
    clean_company = clean_company_name(job.company)
    stem = pattern.replace("{Company}", safe_name(clean_company)).replace(
        "{JobTitle}", safe_name(clean_title)
    )
    timestamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M%S")
    job_dir = root / f"{safe_name(clean_company)}_{safe_name(clean_title)}_{timestamp}"
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / f"{stem}.docx"
    doc.save(path)

    format_check = validate_master_format_contract(path, profile)
    if not format_check["passed"]:
        raise RuntimeError(
            "Generated resume drifted from master formatting contract: "
            + "; ".join(format_check["reasons"])
        )
    return str(path)
