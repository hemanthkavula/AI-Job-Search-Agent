from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import re
import zipfile

from lxml import etree

from app.master_resume import load_master_resume
from app.resume_generator import ROOT, clean_company_name, safe_name

WORD_FORMAT_PATH = ROOT / "data" / "master_word_format.json"
WORD_TEMPLATE_PATH = ROOT / "data" / "Hemanth_Kavula_Senior_Data_Engineer_Resume.docx"
W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_URI}}}"
XMLSPACE = "{http://www.w3.org/XML/1998/namespace}space"
NS = {"w": W_URI}


def load_word_format(path=WORD_FORMAT_PATH):
    data = json.loads(path.read_text(encoding="utf-8"))
    source = data.get("source") or {}
    if source.get("authority") != "user_uploaded_word_format_template":
        raise RuntimeError("Word format record is not user-authoritative")
    if source.get("technical_content_authority") is not False:
        raise RuntimeError("Word template cannot be technical-content authority")
    return data


def _sha(path):
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _template(fmt=None):
    fmt = fmt or load_word_format()
    expected = fmt["source"].get("sha256")
    if not WORD_TEMPLATE_PATH.exists():
        raise RuntimeError(f"Authoritative Word template missing: {WORD_TEMPLATE_PATH}")
    actual = _sha(WORD_TEMPLATE_PATH)
    if expected and actual != expected:
        raise RuntimeError(
            f"Word template checksum mismatch: expected {expected}, got {actual}"
        )
    return WORD_TEMPLATE_PATH


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
    raw = re.sub(
        r"(?i)^\s*(?:immediate interviews?|urgent(?: hiring)?|hiring now)\s*[-:|]\s*",
        "",
        raw,
    )
    raw = re.split(
        r"\s+(?:[-|/]\s*)(?=(?:airflow|dbt|kubernetes|openshift|aws|azure|gcp|snowflake|databricks|hybrid|remote|onsite|on-site)\b)",
        raw,
        1,
        flags=re.I,
    )[0]
    return raw.strip(" -|:/") or "Senior Data Engineer"


def _summary_parts(text):
    text = str(text or "").strip()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) >= 2:
        return [paragraphs[0], " ".join(paragraphs[1:])]
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
    if len(sentences) >= 2:
        split_at = max(1, len(sentences) // 2)
        return [" ".join(sentences[:split_at]), " ".join(sentences[split_at:])]
    if text:
        return [text, ""]
    return ["", ""]


def _terms(generated):
    out = []
    for values in (generated.get("skills") or {}).values():
        for value in values or []:
            value = str(value).strip()
            if value and value.casefold() not in {x.casefold() for x in out}:
                out.append(value)
    return sorted(out, key=len, reverse=True)


def _emphasis(text, generated, limit):
    out = []
    for term in _terms(generated):
        if len(term) >= 3 and re.search(
            r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text, re.I
        ):
            out.append(term)
        if len(out) >= limit:
            break
    if not out:
        words = re.findall(r"\S+", text)
        start = 1 if words and words[0].rstrip(".,:;").lower() in {
            "built", "developed", "designed", "implemented", "modeled", "architected",
            "automated", "enabled", "optimized", "established", "supported", "created",
            "engineered", "delivered", "owned", "maintained",
        } else 0
        if words:
            out = [" ".join(words[start:start + 5]).strip(" ,.;:")]
    return out[:limit]


def _pt(root):
    return root.xpath(".//w:body/w:p", namespaces=NS)


def _text(paragraph):
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS)).strip()


def _between(paragraphs, start_heading, end_heading):
    start = next(i for i, p in enumerate(paragraphs) if _text(p).upper() == start_heading)
    end = next(i for i, p in enumerate(paragraphs) if i > start and _text(p).upper() == end_heading)
    return paragraphs[start + 1:end]


def _rpr(paragraph, bold):
    for run in paragraph.xpath(".//w:r", namespaces=NS):
        if not run.xpath("./w:t", namespaces=NS):
            continue
        has_bold = bool(run.xpath("./w:rPr/w:b|./w:rPr/w:bCs", namespaces=NS))
        if has_bold == bold:
            rpr = run.find(W + "rPr")
            return deepcopy(rpr) if rpr is not None else None
    return None


def _date_rpr(paragraph):
    for run in paragraph.xpath(".//w:r", namespaces=NS):
        text = "".join(run.xpath("./w:t/text()", namespaces=NS))
        if re.search(r"\b20\d{2}\b", text):
            rpr = run.find(W + "rPr")
            return deepcopy(rpr) if rpr is not None else None
    return _rpr(paragraph, False) or _rpr(paragraph, True)


def _clear(paragraph):
    for child in list(paragraph):
        if child.tag != W + "pPr":
            paragraph.remove(child)


def _run(paragraph, text, rpr=None):
    run = etree.SubElement(paragraph, W + "r")
    if rpr is not None:
        run.append(deepcopy(rpr))
    node = etree.SubElement(run, W + "t")
    node.text = text
    if text[:1].isspace() or text[-1:].isspace():
        node.set(XMLSPACE, "preserve")


def _replace(paragraph, text, phrases, normal, bold):
    _clear(paragraph)
    phrases = sorted(dict.fromkeys([x for x in phrases if x]), key=len, reverse=True)
    if not phrases:
        _run(paragraph, text, normal)
        return
    pattern = re.compile("(" + "|".join(re.escape(x) for x in phrases) + ")", re.I)
    lookup = {x.casefold() for x in phrases}
    for part in pattern.split(text):
        if part:
            _run(paragraph, part, bold if part.casefold() in lookup else normal)


def _paragraph_properties(paragraph):
    ppr = paragraph.find(W + "pPr")
    if ppr is None:
        ppr = etree.Element(W + "pPr")
        paragraph.insert(0, ppr)
    return ppr


def _compact_left_paragraph(paragraph, after_twips=40):
    """Remove tab/distributed formatting that creates large visual gaps in Word/PDF."""
    ppr = _paragraph_properties(paragraph)
    tabs = ppr.find(W + "tabs")
    if tabs is not None:
        ppr.remove(tabs)
    for tag in ("keepNext", "keepLines", "pageBreakBefore"):
        node = ppr.find(W + tag)
        if node is not None:
            ppr.remove(node)
    jc = ppr.find(W + "jc")
    if jc is None:
        jc = etree.SubElement(ppr, W + "jc")
    jc.set(W + "val", "left")
    spacing = ppr.find(W + "spacing")
    if spacing is None:
        spacing = etree.SubElement(ppr, W + "spacing")
    spacing.set(W + "before", "0")
    spacing.set(W + "after", str(int(after_twips)))


def _clean_header_layout(paragraph):
    ppr = paragraph.find(W + "pPr")
    jc = None if ppr is None else ppr.find(W + "jc")
    alignment = "" if jc is None else (jc.get(W + "val") or "").lower()
    has_tabs = bool(paragraph.xpath("./w:pPr/w:tabs|.//w:tab", namespaces=NS))
    return not has_tabs and alignment not in {"both", "distribute", "thaiDistribute"}


def _set_right_tab(paragraph, position_twips=10728):
    """Use one right-aligned tab stop for approved master-style title/date rows."""
    ppr = _paragraph_properties(paragraph)
    tabs = ppr.find(W + "tabs")
    if tabs is not None:
        ppr.remove(tabs)
    tabs = etree.SubElement(ppr, W + "tabs")
    tab = etree.SubElement(tabs, W + "tab")
    tab.set(W + "val", "right")
    tab.set(W + "pos", str(int(position_twips)))
    jc = ppr.find(W + "jc")
    if jc is None:
        jc = etree.SubElement(ppr, W + "jc")
    jc.set(W + "val", "left")
    spacing = ppr.find(W + "spacing")
    if spacing is None:
        spacing = etree.SubElement(ppr, W + "spacing")
    spacing.set(W + "before", "0")
    spacing.set(W + "after", "0")


def _tab(paragraph):
    run = etree.SubElement(paragraph, W + "r")
    etree.SubElement(run, W + "tab")


def _has_right_tab(paragraph):
    return bool(
        paragraph.xpath("./w:pPr/w:tabs/w:tab[@w:val='right']", namespaces=NS)
        and paragraph.xpath(".//w:tab", namespaces=NS)
    )


def _normalize_static_headers(root, master):
    """Apply the approved Alpaca/master layout to all fixed-history rows.

    Employer line: Company | Location
    Next line:      Job Title                         Dates (right aligned)
    Education:      School | Location                Dates (right aligned)
    """
    for row in master["experience"]:
        paragraphs = _pt(root)
        company = row["company"]
        header_index = next(i for i, p in enumerate(paragraphs) if _text(p).startswith(company))
        header = paragraphs[header_index]
        company_style = _rpr(header, True) or _rpr(header, False)
        detail_style = _rpr(header, False) or company_style
        date_style = _date_rpr(header) or detail_style

        _compact_left_paragraph(header, after_twips=0)
        _clear(header)
        _run(header, company, company_style)
        _run(header, f" | {row['location']}", detail_style)

        paragraphs = _pt(root)
        header_index = next(i for i, p in enumerate(paragraphs) if _text(p) == f"{company} | {row['location']}")
        roles_index = next(
            i for i in range(header_index + 1, len(paragraphs))
            if _text(paragraphs[i]) == "Roles & Responsibilities:"
        )
        title = str(row.get("title") or "").strip()
        title_paragraph = next(
            p for p in paragraphs[header_index + 1:roles_index]
            if _text(p) == title
        )
        title_style = _rpr(title_paragraph, False) or _rpr(title_paragraph, True)
        _set_right_tab(title_paragraph)
        _clear(title_paragraph)
        _run(title_paragraph, title, title_style)
        _tab(title_paragraph)
        _run(title_paragraph, str(row.get("dates") or "").strip(), date_style)

    for row in master.get("education") or []:
        school = str(row.get("school") or "").strip()
        location = str(row.get("location") or "").strip()
        if not school:
            continue
        paragraph = next((p for p in _pt(root) if _text(p).startswith(school)), None)
        if paragraph is None:
            continue
        style = _rpr(paragraph, False) or _rpr(paragraph, True)
        date_style = _date_rpr(paragraph) or style
        start = str(row.get("start") or "").strip()
        end = str(row.get("end") or "").strip()
        dates = f"{start} – {end}" if start and end else (start or end)
        _set_right_tab(paragraph)
        _clear(paragraph)
        _run(paragraph, school, style)
        if location:
            _run(paragraph, f" | {location}", style)
        _tab(paragraph)
        _run(paragraph, dates, date_style)


def _is_employer_footer(value):
    return value.startswith("Environment:") or value.startswith("Skills:")


def _exp(paragraphs):
    master = load_master_resume()
    out = {}
    for row in master["experience"]:
        company = row["company"]
        header_index = next(i for i, paragraph in enumerate(paragraphs) if _text(paragraph).startswith(company))
        roles_index = next(
            i for i in range(header_index + 1, len(paragraphs))
            if _text(paragraphs[i]) == "Roles & Responsibilities:"
        )
        bullets = []
        footer = None
        for paragraph in paragraphs[roles_index + 1:]:
            value = _text(paragraph)
            if _is_employer_footer(value):
                footer = paragraph
                break
            if value:
                bullets.append(paragraph)
        if len(bullets) != len(row["bullets"]) or footer is None:
            raise RuntimeError(f"Word template experience structure mismatch for {company}")
        out[company] = {"bullets": bullets, "footer": footer}
    return out


def _write_docx(template, out, xml):
    with zipfile.ZipFile(template, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info, xml if info.filename == "word/document.xml" else zin.read(info.filename))


def _same_non_document_parts(a, b):
    with zipfile.ZipFile(a) as za, zipfile.ZipFile(b) as zb:
        names_a = {x.filename for x in za.infolist()}
        names_b = {x.filename for x in zb.infolist()}
        if names_a != names_b:
            return False
        return all(za.read(name) == zb.read(name) for name in names_a if name != "word/document.xml")


def _no_page_breaks(root):
    return not root.xpath(".//w:pageBreakBefore|.//w:br[@w:type='page']", namespaces=NS)


def _ppr(paragraph):
    value = paragraph.find(W + "pPr")
    return b"" if value is None else etree.tostring(value)


def _xml(path):
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read("word/document.xml"))


def _paragraph_formats_match(rows, template_rows):
    if not rows or not template_rows:
        return False
    for index, paragraph in enumerate(rows):
        reference = template_rows[min(index, len(template_rows) - 1)]
        if _ppr(paragraph) != _ppr(reference):
            return False
    return True


def validate_master_format_contract(path, master=None, word_format=None):
    master = master or load_master_resume()
    fmt = word_format or load_word_format()
    template = _template(fmt)
    reasons = []
    if not _same_non_document_parts(template, path):
        reasons.append("non_document_word_package_changed")
    source_root = _xml(template)
    output_root = _xml(path)
    source_paragraphs = _pt(source_root)
    output_paragraphs = _pt(output_root)
    if etree.tostring(source_root.find(".//" + W + "sectPr")) != etree.tostring(output_root.find(".//" + W + "sectPr")):
        reasons.append("section_properties_changed")
    if not _no_page_breaks(output_root):
        reasons.append("forced_page_break")
    for heading in ("PROFESSIONAL SUMMARY", "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE", "EDUCATION"):
        source = next((p for p in source_paragraphs if _text(p).upper() == heading), None)
        output = next((p for p in output_paragraphs if _text(p).upper() == heading), None)
        if source is None or output is None:
            reasons.append("heading_" + heading)
        elif etree.tostring(source) != etree.tostring(output):
            reasons.append("heading_format_" + heading)
    summary_rows = [p for p in _between(output_paragraphs, "PROFESSIONAL SUMMARY", "TECHNICAL SKILLS") if _text(p)]
    source_summary_rows = [p for p in _between(source_paragraphs, "PROFESSIONAL SUMMARY", "TECHNICAL SKILLS") if _text(p)]
    if len(summary_rows) != 2:
        reasons.append("summary_structure")
    elif not _paragraph_formats_match(summary_rows, source_summary_rows):
        reasons.append("summary_paragraph_format")
    skill_rows = [p for p in _between(output_paragraphs, "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE") if _text(p)]
    source_skill_rows = [p for p in _between(source_paragraphs, "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE") if _text(p)]
    if not skill_rows:
        reasons.append("skills_structure")
    elif not _paragraph_formats_match(skill_rows, source_skill_rows):
        reasons.append("skills_paragraph_format")

    for row in master["experience"]:
        expected = f"{row['company']} | {row['location']}"
        header_index = next((i for i, p in enumerate(output_paragraphs) if _text(p).startswith(row["company"])), None)
        header = None if header_index is None else output_paragraphs[header_index]
        if header is None or _text(header) != expected:
            reasons.append(row["company"] + "_header_text")
        elif not _clean_header_layout(header):
            reasons.append(row["company"] + "_header_spacing")
        roles_index = next(
            (i for i in range((header_index or 0) + 1, len(output_paragraphs)) if _text(output_paragraphs[i]) == "Roles & Responsibilities:"),
            None,
        )
        title_date = None if header_index is None or roles_index is None else next(
            (
                p for p in output_paragraphs[header_index + 1:roles_index]
                if _text(p) == f"{row.get('title', '')}{row.get('dates', '')}"
            ),
            None,
        )
        if title_date is None:
            reasons.append(row["company"] + "_title_date_text")
        elif not _has_right_tab(title_date):
            reasons.append(row["company"] + "_title_date_alignment")

    for row in master.get("education") or []:
        school = str(row.get("school") or "").strip()
        location = str(row.get("location") or "").strip()
        start = str(row.get("start") or "").strip()
        end = str(row.get("end") or "").strip()
        dates = f"{start} – {end}" if start and end else (start or end)
        school_location = f"{school} | {location}" if location else school
        expected = f"{school_location}{dates}"
        school_index = next((i for i, p in enumerate(output_paragraphs) if _text(p).startswith(school)), None)
        paragraph = None if school_index is None else output_paragraphs[school_index]
        if paragraph is None or _text(paragraph) != expected:
            reasons.append("education_school_location_date_text")
        elif not _has_right_tab(paragraph):
            reasons.append("education_date_alignment")

    output_experience = _exp(output_paragraphs)
    source_experience = _exp(source_paragraphs)
    for row in master["experience"]:
        company = row["company"]
        if len(output_experience[company]["bullets"]) != len(row["bullets"]):
            reasons.append(company + "_bullet_count")
        if any(
            _ppr(paragraph) != _ppr(source_experience[company]["bullets"][index])
            for index, paragraph in enumerate(output_experience[company]["bullets"])
        ):
            reasons.append(company + "_bullet_format")
        if _ppr(output_experience[company]["footer"]) != _ppr(source_experience[company]["footer"]):
            reasons.append(company + "_environment_footer_format")
        if not _text(output_experience[company]["footer"]).startswith("Environment: "):
            reasons.append(company + "_environment_footer_label")
    return {
        "passed": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "format_authority": "user_uploaded_word_format_template",
        "format_source": "live_user_uploaded_docx_template",
        "word_template_sha256": fmt["source"].get("sha256"),
        "content_length_policy": "compact_master_like_layout",
    }


def _out(job, directory):
    root = ROOT / directory
    root.mkdir(parents=True, exist_ok=True)
    company = clean_company_name(job.company)
    title = canonical_resume_title(job.title)
    stem = f"Hemanth_Kavula_{safe_name(company)}_{safe_name(title)}"
    timestamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M%S")
    folder = root / f"{safe_name(company)}_{safe_name(title)}_{timestamp}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{stem}.docx"


def _ensure_skill_rows(root, needed):
    paragraphs = _pt(root)
    skill_rows = [p for p in _between(paragraphs, "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE") if _text(p)]
    if not skill_rows:
        raise RuntimeError("Word template has no Technical Skills rows")
    body = root.find(".//" + W + "body")
    if needed > len(skill_rows):
        anchor = next(p for p in _pt(root) if _text(p).upper() == "PROFESSIONAL EXPERIENCE")
        insert_at = body.index(anchor)
        source = skill_rows[-1]
        for _ in range(needed - len(skill_rows)):
            clone = deepcopy(source)
            _clear(clone)
            body.insert(insert_at, clone)
            insert_at += 1
    paragraphs = _pt(root)
    return [
        p for p in _between(paragraphs, "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE")
        if _text(p) or p.find(W + "pPr") is not None
    ]


def _footer_styles(source_layout):
    source_footers = [x["footer"] for x in source_layout.values()]
    bold = next((_rpr(p, True) for p in source_footers if _rpr(p, True) is not None), None)
    normal = next((_rpr(p, False) for p in source_footers if _rpr(p, False) is not None), None)
    return bold, normal


def _write_skills_footer(paragraph, values, bold_style, normal_style):
    values = [str(value).strip() for value in values or [] if str(value).strip()]
    if not values:
        raise RuntimeError("Employer environment technology list is empty")
    _clear(paragraph)
    _run(paragraph, "Environment", bold_style)
    _run(paragraph, ": " + ", ".join(values), normal_style)


def _master_mode_with_skills_footer(template, out):
    master = load_master_resume()
    with zipfile.ZipFile(template) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    _normalize_static_headers(root, master)
    layout = _exp(_pt(root))
    source_layout = _exp(_pt(_xml(template)))
    footer_bold, footer_normal = _footer_styles(source_layout)
    for row in master["experience"]:
        text = str(row.get("environment") or "").strip()
        values = [text] if text else []
        _write_skills_footer(layout[row["company"]]["footer"], values, footer_bold, footer_normal)
    xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")
    _write_docx(template, out, xml)
    check = validate_master_format_contract(out, master)
    if not check["passed"]:
        raise RuntimeError(
            "Generated master-mode resume violated Word-template format contract: " + "; ".join(check["reasons"])
        )
    return str(out)


def render_llm_resume(job, profile, generated, output_dir="generated/resumes"):
    fmt = load_word_format()
    template = _template(fmt)
    out = _out(job, output_dir)
    if generated.get("_master_mode"):
        return _master_mode_with_skills_footer(template, out)
    master = load_master_resume()
    with zipfile.ZipFile(template) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    _normalize_static_headers(root, master)
    paragraphs = _pt(root)
    header = paragraphs[1]
    normal = _rpr(header, False)
    _clear(header)
    _run(header, canonical_resume_title(job.title), normal)
    summary_rows = [p for p in _between(paragraphs, "PROFESSIONAL SUMMARY", "TECHNICAL SKILLS") if _text(p)]
    parts = _summary_parts(generated.get("summary", ""))
    if len(summary_rows) < 2:
        raise RuntimeError("Word template must contain two Professional Summary paragraphs")
    summary_normal = _rpr(summary_rows[0], False) or _rpr(summary_rows[1], False)
    summary_bold = _rpr(summary_rows[0], True) or _rpr(summary_rows[1], True)
    for paragraph, text in zip(summary_rows[:2], parts):
        _replace(paragraph, text, _emphasis(text, generated, 5), summary_normal, summary_bold)
    items = list((generated.get("skills") or {}).items())
    if not items:
        raise RuntimeError("Generated Technical Skills section is empty")
    skill_rows = _ensure_skill_rows(root, len(items))
    skill_bold = _rpr(skill_rows[0], True)
    skill_normal = _rpr(skill_rows[0], False)
    for paragraph, (category, values) in zip(skill_rows, items):
        _clear(paragraph)
        _run(paragraph, str(category), skill_bold)
        _run(paragraph, ": ", skill_normal)
        _run(paragraph, ", ".join(str(value) for value in values or []), skill_normal)
    body = root.find(".//" + W + "body")
    for paragraph in skill_rows[len(items):]:
        body.remove(paragraph)
    paragraphs = _pt(root)
    layout = _exp(paragraphs)
    source_root = _xml(template)
    source_layout = _exp(_pt(source_root))
    all_source_bullets = [paragraph for employer in source_layout.values() for paragraph in employer["bullets"]]
    bullet_normal = next((_rpr(p, False) for p in all_source_bullets if _rpr(p, False) is not None), None)
    bullet_bold = next((_rpr(p, True) for p in all_source_bullets if _rpr(p, True) is not None), None)
    footer_bold, footer_normal = _footer_styles(source_layout)
    generated_by_company = {item.get("company"): item for item in generated.get("experience") or []}
    for row in master["experience"]:
        company = row["company"]
        item = generated_by_company.get(company)
        if not item:
            raise RuntimeError(f"Generated experience missing {company}")
        bullets = [str(value).strip() for value in item.get("bullets") or []]
        if len(bullets) != len(row["bullets"]):
            raise RuntimeError(f"{company} must contain exactly {len(row['bullets'])} bullets")
        for paragraph, text in zip(layout[company]["bullets"], bullets):
            _replace(paragraph, text, _emphasis(text, generated, 2), bullet_normal, bullet_bold)
        skills_used = item.get("skills_used")
        if not skills_used:
            legacy = str(item.get("environment") or "").strip()
            skills_used = [legacy] if legacy else []
        _write_skills_footer(layout[company]["footer"], skills_used, footer_bold, footer_normal)
    xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")
    _write_docx(template, out, xml)
    check = validate_master_format_contract(out, master, fmt)
    if not check["passed"]:
        raise RuntimeError(
            "Generated resume violated live Word-template format contract: " + "; ".join(check["reasons"])
        )
    return str(out)