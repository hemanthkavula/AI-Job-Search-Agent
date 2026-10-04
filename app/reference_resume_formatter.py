from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from app.master_resume import load_master_resume
from app.resume_generator import ROOT, clean_company_name, safe_name


def _rgb(value: str) -> RGBColor:
    return RGBColor.from_string(str(value).lstrip("#").upper())


def _run(run, style, size=None, bold=False, color=None, underline=False):
    run.font.name = style["font"]
    run.font.size = Pt(float(size if size is not None else style["body_pt"]))
    run.bold = bool(bold)
    run.underline = bool(underline)
    if color is not None:
        run.font.color.rgb = color
    return run


def _compact(paragraph, before=0, after=0, line=1.0):
    paragraph.paragraph_format.space_before = Pt(float(before))
    paragraph.paragraph_format.space_after = Pt(float(after))
    paragraph.paragraph_format.line_spacing = float(line)


def _section(doc, label, style, after=None):
    p = doc.add_paragraph()
    _compact(
        p,
        style["section_before_pt"],
        style["section_after_pt"] if after is None else after,
    )
    p.paragraph_format.keep_with_next = True
    _run(
        p.add_run(label),
        style,
        style["section_heading_pt"],
        True,
        _rgb(style["dark_blue_hex"]),
    )
    p_pr = p._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), str(style["rule_blue_hex"]).upper())
    p_bdr.append(bottom)
    p_pr.append(p_bdr)
    return p


def canonical_resume_title(title):
    raw = re.sub(r"\s+", " ", str(title or "")).strip()
    match = re.search(
        r"(?i)\b(?:(principal|staff|lead|senior|sr\.?|junior|jr\.?)\s+)?data\s+engineer(?:ing)?\b",
        raw,
    )
    if match:
        level = (match.group(1) or "").lower().rstrip(".")
        level = {"sr": "Senior", "jr": "Junior"}.get(level, level.title())
        core = "Data Engineering" if "engineering" in match.group(0).lower() else "Data Engineer"
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


def _summary_parts(text):
    text = str(text or "").strip()
    explicit = [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()]
    if len(explicit) >= 2:
        return explicit[:2]
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
    if len(sentences) >= 4:
        midpoint = max(1, len(sentences) // 2)
        return [" ".join(sentences[:midpoint]), " ".join(sentences[midpoint:])]
    if len(sentences) == 3:
        return [sentences[0], " ".join(sentences[1:])]
    if len(sentences) == 2:
        return sentences
    return [text] if text else []


def _technical_terms(generated):
    terms = []
    for values in (generated.get("skills") or {}).values():
        for value in values or []:
            term = str(value).strip()
            if term and term.casefold() not in {x.casefold() for x in terms}:
                terms.append(term)
    return sorted(terms, key=len, reverse=True)


def _metric_terms(text):
    patterns = [
        r"~?\d+(?:\.\d+)?\s*[–-]\s*\d+(?:\.\d+)?\s*(?:GB/day|GB|TB|%|M|million)",
        r"~?\d+(?:\.\d+)?\s*(?:GB/day|GB|TB|%|M|million)",
        r"\d+\+\s*rules",
    ]
    out = []
    for pattern in patterns:
        out.extend(m.group(0) for m in re.finditer(pattern, str(text), flags=re.I))
    return list(dict.fromkeys(out))


def _fallback_phrase(text):
    words = re.findall(r"\S+", str(text or ""))
    if len(words) <= 2:
        return " ".join(words)
    start = 1 if words[0].rstrip(".,:;").lower() in {
        "built", "developed", "designed", "implemented", "modeled", "architected",
        "automated", "enabled", "optimized", "established", "supported", "created",
        "engineered", "delivered", "owned", "maintained",
    } else 0
    end = min(len(words), start + 5)
    return " ".join(words[start:end]).strip(" ,.;:")


def _emphasis_for_text(text, generated, explicit=None, max_terms=2):
    if explicit:
        matches = [str(x) for x in explicit if str(x).strip() and str(x).casefold() in str(text).casefold()]
        if matches:
            return matches[:max_terms]
    matches = []
    for metric in _metric_terms(text):
        if metric.casefold() not in {x.casefold() for x in matches}:
            matches.append(metric)
    for term in _technical_terms(generated):
        if len(term) < 3:
            continue
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", str(text), flags=re.I):
            if term.casefold() not in {x.casefold() for x in matches}:
                matches.append(term)
        if len(matches) >= max_terms:
            break
    if not matches:
        phrase = _fallback_phrase(text)
        if phrase:
            matches.append(phrase)
    return matches[:max_terms]


def _emphasis_runs(paragraph, text, phrases, style, size):
    text = str(text or "")
    phrases = [str(x).strip() for x in phrases or [] if str(x).strip()]
    phrases = sorted(dict.fromkeys(phrases), key=len, reverse=True)
    if not phrases:
        _run(paragraph.add_run(text), style, size)
        return
    pattern = re.compile("(" + "|".join(re.escape(x) for x in phrases) + ")", flags=re.I)
    lookup = {x.casefold() for x in phrases}
    for part in pattern.split(text):
        if part:
            _run(paragraph.add_run(part), style, size, part.casefold() in lookup)


def _company_header(doc, fixed, style):
    p = doc.add_paragraph()
    _compact(p, 6, 0)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.tab_stops.add_tab_stop(Inches(float(style["right_tab_in"])), WD_TAB_ALIGNMENT.RIGHT)
    _run(p.add_run(fixed["company"]), style, style["company_pt"], True)
    _run(p.add_run(" | " + fixed["location"]), style, style["body_pt"])
    _run(
        p.add_run("\t" + fixed["dates"]),
        style,
        style["body_pt"],
        False,
        _rgb(style["date_gray_hex"]),
    )

    title = doc.add_paragraph()
    _compact(title, 0, 1)
    title.paragraph_format.keep_with_next = True
    _run(
        title.add_run(fixed["title"]),
        style,
        style["job_title_pt"],
        True,
        _rgb(style["job_blue_hex"]),
    )

    roles = doc.add_paragraph()
    _compact(roles, 0, 1)
    roles.paragraph_format.keep_with_next = True
    _run(roles.add_run("Roles & Responsibilities:"), style, style["body_pt"], True)
    return roles


def _environment_value(item, generated):
    value = str(item.get("environment") or "").strip()
    if value:
        return value
    terms = list(reversed(_technical_terms(generated)))
    terms = [x for x in terms if len(x) >= 2]
    return ", ".join(terms[:14])


def _expected_counts(master):
    return {row["company"]: len(row["bullets"]) for row in master["experience"]}


def _length_close(value, expected_inches, tolerance=0.015):
    return value is not None and abs(value.inches - float(expected_inches)) <= tolerance


def validate_master_format_contract(path, master=None):
    """Validate the structural/visual invariants measured from the uploaded master PDF."""
    master = master or load_master_resume()
    style = master["style"]
    expected_counts = _expected_counts(master)
    doc = Document(path)
    paras = doc.paragraphs
    reasons = []

    normal = doc.styles["Normal"]
    if normal.font.name != style["font"]:
        reasons.append("normal_font")
    if normal.font.size != Pt(float(style["body_pt"])):
        reasons.append("normal_size")

    section = doc.sections[0]
    for key, actual in {
        "top_margin_in": section.top_margin.inches,
        "bottom_margin_in": section.bottom_margin.inches,
        "left_margin_in": section.left_margin.inches,
        "right_margin_in": section.right_margin.inches,
    }.items():
        if abs(actual - float(style[key])) > 0.02:
            reasons.append(key)

    expected_sections = ["PROFESSIONAL SUMMARY", "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE", "EDUCATION"]
    for label in expected_sections:
        matches = [p for p in paras if p.text.strip() == label]
        if len(matches) != 1:
            reasons.append(f"section_{label}")
            continue
        run = matches[0].runs[0] if matches[0].runs else None
        if not run or not run.bold or run.font.size != Pt(float(style["section_heading_pt"])):
            reasons.append(f"section_style_{label}")

    try:
        start = paras.index(next(p for p in paras if p.text.strip() == "PROFESSIONAL SUMMARY")) + 1
        end = paras.index(next(p for p in paras if p.text.strip() == "TECHNICAL SKILLS"))
        summary_paras = [p for p in paras[start:end] if p.text.strip()]
        if len(summary_paras) != 2:
            reasons.append("summary_paragraph_count")
        if not any(run.bold for p in summary_paras for run in p.runs if run.text.strip()):
            reasons.append("summary_selective_bold")
    except StopIteration:
        pass

    if sum(p.text.strip() == "Roles & Responsibilities:" for p in paras) != 3:
        reasons.append("roles_labels")
    if sum(p.text.startswith("Environment: ") for p in paras) != 3:
        reasons.append("environment_lines")

    current = None
    counts = {company: 0 for company in expected_counts}
    fidelity_bullets = []
    for p in paras:
        for company in expected_counts:
            if p.text.startswith(company):
                current = company
                break
        else:
            if current and p.style and "List Bullet" in p.style.name:
                counts[current] += 1
                if not _length_close(p.paragraph_format.left_indent, style["bullet_left_indent_in"]):
                    reasons.append(f"{current}_left_indent")
                if not _length_close(p.paragraph_format.first_line_indent, style["bullet_hanging_indent_in"]):
                    reasons.append(f"{current}_hanging_indent")
                if not any(run.bold for run in p.runs if run.text.strip()):
                    reasons.append(f"{current}_bullet_missing_emphasis")
                if current == "Fidelity Investments":
                    fidelity_bullets.append(p)

    if counts != expected_counts:
        reasons.append(f"bullet_counts={counts}")
    break_before = int(style.get("fidelity_page_break_before_bullet") or 0)
    if break_before and len(fidelity_bullets) >= break_before:
        if fidelity_bullets[break_before - 1].paragraph_format.page_break_before is not True:
            reasons.append("fidelity_page_break")

    return {"passed": not reasons, "reasons": list(dict.fromkeys(reasons)), "source_sha256": master["source"]["sha256"]}


def render_llm_resume(job, profile, generated, output_dir="generated/resumes"):
    """Render master or JD-tailored content using the uploaded master PDF's measured format."""
    master = load_master_resume()
    style = master["style"]
    identity = master["identity"]
    fixed_by_company = {row["company"]: row for row in master["experience"]}
    master_mode = bool(generated.get("_master_mode"))

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(float(style["top_margin_in"]))
    section.bottom_margin = Inches(float(style["bottom_margin_in"]))
    section.left_margin = Inches(float(style["left_margin_in"]))
    section.right_margin = Inches(float(style["right_margin_in"]))

    normal = doc.styles["Normal"]
    normal.font.name = style["font"]
    normal.font.size = Pt(float(style["body_pt"]))
    normal.paragraph_format.space_after = Pt(0)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _compact(p, 0, 2.5)
    _run(p.add_run(identity["name"]), style, style["name_pt"], True, _rgb(style["dark_blue_hex"]))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _compact(p, 0, 3)
    headline = identity["headline"] if master_mode else canonical_resume_title(job.title)
    _run(p.add_run(headline), style, style["headline_pt"], False, _rgb(style["dark_blue_hex"]))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _compact(p, 0, 7)
    contact = identity["contact"]
    values = [contact.get("phone"), contact.get("email"), contact.get("linkedin")]
    values = [x for x in values if x]
    for index, value in enumerate(values):
        if index:
            _run(p.add_run(" | "), style, style["contact_pt"])
        is_link = "@" in value or "linkedin" in value.lower()
        _run(
            p.add_run(value),
            style,
            style["contact_pt"],
            False,
            _rgb(style["link_hex"]) if is_link else None,
            is_link,
        )

    _section(doc, "PROFESSIONAL SUMMARY", style, 4)
    parts = _summary_parts(generated.get("summary", ""))
    summary_explicit = generated.get("summary_emphasis") if master_mode else None
    for index, part in enumerate(parts):
        p = doc.add_paragraph()
        after = style["summary_first_after_pt"] if index == 0 else style["summary_last_after_pt"]
        _compact(p, 0, after, style["summary_line_spacing"])
        phrases = _emphasis_for_text(part, generated, summary_explicit, max_terms=5)
        _emphasis_runs(p, part, phrases, style, style["summary_pt"])

    _section(doc, "TECHNICAL SKILLS", style, 6)
    for label, values in (generated.get("skills") or {}).items():
        p = doc.add_paragraph()
        _compact(p, 0, 0.2, 1.0)
        _run(p.add_run(str(label) + ": "), style, style["body_pt"], True)
        _run(p.add_run(", ".join(str(v) for v in values or [])), style, style["body_pt"])

    _section(doc, "PROFESSIONAL EXPERIENCE", style, 4)
    expected_counts = _expected_counts(master)
    for item in generated.get("experience") or []:
        company = item.get("company")
        fixed = fixed_by_company.get(company)
        if not fixed:
            continue
        roles = _company_header(doc, fixed, style)
        bullets = list(item.get("bullets") or [])[: expected_counts[company]]
        explicit_rows = item.get("bullet_emphasis") if master_mode else None
        for index, line in enumerate(bullets):
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.left_indent = Inches(float(style["bullet_left_indent_in"]))
            p.paragraph_format.first_line_indent = Inches(float(style["bullet_hanging_indent_in"]))
            p.paragraph_format.keep_together = True
            _compact(p, 0, style["bullet_after_pt"], 1.0)
            break_before = int(style.get("fidelity_page_break_before_bullet") or 0)
            if company == "Fidelity Investments" and break_before and index == break_before - 1:
                p.paragraph_format.page_break_before = True
            explicit = explicit_rows[index] if explicit_rows and index < len(explicit_rows) else None
            phrases = _emphasis_for_text(str(line), generated, explicit, max_terms=2)
            _emphasis_runs(p, str(line).strip(), phrases, style, style["body_pt"])
        if not bullets:
            roles.paragraph_format.keep_with_next = False

        env = doc.add_paragraph()
        _compact(env, 1, style["environment_after_pt"])
        _run(env.add_run("Environment: "), style, style["body_pt"], True)
        _run(env.add_run(_environment_value(item, generated)), style, style["body_pt"])

    _section(doc, "EDUCATION", style, 4)
    for education in master["education"]:
        p = doc.add_paragraph()
        _compact(p, 0, 1)
        p.paragraph_format.keep_with_next = True
        _run(p.add_run(education["degree"]), style, style["education_degree_pt"], True)

        p = doc.add_paragraph()
        _compact(p, 0, 0)
        p.paragraph_format.tab_stops.add_tab_stop(Inches(float(style["right_tab_in"])), WD_TAB_ALIGNMENT.RIGHT)
        _run(p.add_run(f"{education['school']} | {education['location']}"), style, style["body_pt"])
        _run(
            p.add_run("\t" + f"{education['start']} – {education['end']}"),
            style,
            style["body_pt"],
            False,
            _rgb(style["date_gray_hex"]),
        )

    root = ROOT / output_dir
    root.mkdir(parents=True, exist_ok=True)
    clean_company = clean_company_name(job.company)
    clean_title = canonical_resume_title(job.title)
    stem = f"Hemanth_Kavula_{safe_name(clean_company)}_{safe_name(clean_title)}"
    timestamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M%S")
    job_dir = root / f"{safe_name(clean_company)}_{safe_name(clean_title)}_{timestamp}"
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / f"{stem}.docx"
    doc.save(path)

    contract = validate_master_format_contract(path, master)
    if not contract["passed"]:
        raise RuntimeError("Generated resume violated master format contract: " + "; ".join(contract["reasons"]))
    return str(path)
