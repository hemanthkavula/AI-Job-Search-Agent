from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import zipfile

from lxml import etree

from app.master_resume import load_master_resume

W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_URI}}}"
NS = {"w": W_URI}


FULL_TEXT_WIDTH_TWIPS = 10800
LEFT_COLUMN_TWIPS = 8352
RIGHT_COLUMN_TWIPS = 2448


def _text(node) -> str:
    return "".join(node.xpath(".//w:t/text()", namespaces=NS)).strip()


def _ppr(paragraph):
    ppr = paragraph.find(W + "pPr")
    if ppr is None:
        ppr = etree.Element(W + "pPr")
        paragraph.insert(0, ppr)
    return ppr


def _set_flag(paragraph, tag: str, enabled: bool) -> None:
    ppr = _ppr(paragraph)
    node = ppr.find(W + tag)
    if enabled:
        if node is None:
            etree.SubElement(ppr, W + tag)
    elif node is not None:
        ppr.remove(node)


def _has_flag(paragraph, tag: str) -> bool:
    ppr = paragraph.find(W + "pPr")
    return ppr is not None and ppr.find(W + tag) is not None


def _set_zero_left_indent(paragraph) -> None:
    """Make fixed resume rows share one exact left edge."""
    ppr = _ppr(paragraph)
    ind = ppr.find(W + "ind")
    if ind is None:
        ind = etree.SubElement(ppr, W + "ind")
    ind.set(W + "left", "0")
    ind.set(W + "start", "0")
    for attr in ("firstLine", "hanging"):
        key = W + attr
        if key in ind.attrib:
            del ind.attrib[key]


def _has_zero_left_indent(paragraph) -> bool:
    ppr = paragraph.find(W + "pPr")
    if ppr is None:
        return True
    ind = ppr.find(W + "ind")
    if ind is None:
        return True
    left = ind.get(W + "left")
    start = ind.get(W + "start")
    first_line = ind.get(W + "firstLine")
    hanging = ind.get(W + "hanging")
    return (
        left in (None, "0")
        and start in (None, "0")
        and first_line in (None, "0")
        and hanging in (None, "0")
    )


def _remove_forced_breaks(paragraph) -> None:
    _set_flag(paragraph, "pageBreakBefore", False)
    for br in list(paragraph.xpath(".//w:br[@w:type='page']", namespaces=NS)):
        parent = br.getparent()
        if parent is not None:
            parent.remove(br)


def _set_row_cant_split(row) -> None:
    trpr = row.find(W + "trPr")
    if trpr is None:
        trpr = etree.Element(W + "trPr")
        row.insert(0, trpr)
    if trpr.find(W + "cantSplit") is None:
        etree.SubElement(trpr, W + "cantSplit")


def _set_zero_cell_margins(container) -> None:
    for side in ("top", "left", "bottom", "right"):
        node = container.find(W + side)
        if node is None:
            node = etree.SubElement(container, W + side)
        node.set(W + "type", "dxa")
        node.set(W + "w", "0")


def _normalize_header_table(table) -> None:
    """Match the final approved resume's full-width, flush-left two-column rows."""
    if table is None:
        return
    tblpr = table.find(W + "tblPr")
    if tblpr is None:
        tblpr = etree.Element(W + "tblPr")
        table.insert(0, tblpr)

    tblw = tblpr.find(W + "tblW")
    if tblw is None:
        tblw = etree.SubElement(tblpr, W + "tblW")
    tblw.set(W + "type", "dxa")
    tblw.set(W + "w", str(FULL_TEXT_WIDTH_TWIPS))

    jc = tblpr.find(W + "jc")
    if jc is None:
        jc = etree.SubElement(tblpr, W + "jc")
    jc.set(W + "val", "left")

    tblind = tblpr.find(W + "tblInd")
    if tblind is None:
        tblind = etree.SubElement(tblpr, W + "tblInd")
    tblind.set(W + "type", "dxa")
    tblind.set(W + "w", "0")

    tbl_cell_mar = tblpr.find(W + "tblCellMar")
    if tbl_cell_mar is None:
        tbl_cell_mar = etree.SubElement(tblpr, W + "tblCellMar")
    _set_zero_cell_margins(tbl_cell_mar)

    cells = table.xpath(".//w:tr[1]/w:tc", namespaces=NS)
    if len(cells) >= 2:
        grid = table.find(W + "tblGrid")
        if grid is None:
            grid = etree.SubElement(table, W + "tblGrid")
        for child in list(grid):
            grid.remove(child)
        for width in (LEFT_COLUMN_TWIPS, RIGHT_COLUMN_TWIPS):
            col = etree.SubElement(grid, W + "gridCol")
            col.set(W + "w", str(width))

    for index, cell in enumerate(cells[:2]):
        tcpr = cell.find(W + "tcPr")
        if tcpr is None:
            tcpr = etree.Element(W + "tcPr")
            cell.insert(0, tcpr)
        tcw = tcpr.find(W + "tcW")
        if tcw is None:
            tcw = etree.SubElement(tcpr, W + "tcW")
        tcw.set(W + "type", "dxa")
        tcw.set(W + "w", str(LEFT_COLUMN_TWIPS if index == 0 else RIGHT_COLUMN_TWIPS))

        tcmar = tcpr.find(W + "tcMar")
        if tcmar is None:
            tcmar = etree.SubElement(tcpr, W + "tcMar")
        for side in ("top", "start", "bottom", "end", "left", "right"):
            node = tcmar.find(W + side)
            if node is None:
                node = etree.SubElement(tcmar, W + side)
            node.set(W + "type", "dxa")
            node.set(W + "w", "0")

        for paragraph in cell.xpath("./w:p", namespaces=NS):
            _set_zero_left_indent(paragraph)


def _header_table_is_left_aligned(table) -> bool:
    if table is None:
        return True
    tblpr = table.find(W + "tblPr")
    if tblpr is None:
        return True
    jc = tblpr.find(W + "jc")
    if jc is not None and (jc.get(W + "val") or "").lower() not in ("", "left", "start"):
        return False
    tblind = tblpr.find(W + "tblInd")
    if tblind is not None and tblind.get(W + "w") not in (None, "0"):
        return False
    tblw = tblpr.find(W + "tblW")
    if tblw is not None and tblw.get(W + "type") == "dxa" and tblw.get(W + "w") not in (None, str(FULL_TEXT_WIDTH_TWIPS)):
        return False
    return True


def _top_level_paragraphs(body):
    return [child for child in body if child.tag == W + "p"]


def _first_nonempty_paragraph(children, start_index: int):
    for child in children[start_index:]:
        if child.tag == W + "p" and _text(child):
            return child
    return None


def _locate_paragraph_block(root, company: str):
    body = root.find(".//" + W + "body")
    if body is None:
        return None
    paragraphs = _top_level_paragraphs(body)
    try:
        header_index = next(i for i, p in enumerate(paragraphs) if _text(p).startswith(company))
    except StopIteration:
        return None
    try:
        roles_index = next(
            i for i in range(header_index + 1, len(paragraphs))
            if _text(paragraphs[i]) == "Roles & Responsibilities:"
        )
    except StopIteration:
        return None
    title = next((p for p in paragraphs[header_index + 1:roles_index] if _text(p)), None)
    if title is None:
        return None
    first_bullet = next(
        (
            p for p in paragraphs[roles_index + 1:]
            if _text(p) and not _text(p).startswith(("Environment:", "Skills:"))
        ),
        None,
    )
    if first_bullet is None:
        return None
    return {
        "kind": "paragraph",
        "header_paragraphs": [paragraphs[header_index]],
        "header_table": None,
        "title": title,
        "roles": paragraphs[roles_index],
        "first_bullet": first_bullet,
    }


def _locate_table_block(root, company: str):
    body = root.find(".//" + W + "body")
    if body is None:
        return None
    children = list(body)
    table_index = None
    table = None
    for index, child in enumerate(children):
        if child.tag == W + "tbl" and _text(child).startswith(company):
            table_index = index
            table = child
            break
    if table is None:
        return None
    header_paragraphs = table.xpath(".//w:tr[1]/w:tc/w:p", namespaces=NS)
    title = _first_nonempty_paragraph(children, table_index + 1)
    if title is None:
        return None
    title_index = children.index(title)
    roles = _first_nonempty_paragraph(children, title_index + 1)
    if roles is None or _text(roles) != "Roles & Responsibilities:":
        return None
    roles_index = children.index(roles)
    first_bullet = _first_nonempty_paragraph(children, roles_index + 1)
    if first_bullet is None:
        return None
    first_row = table.find(".//" + W + "tr")
    return {
        "kind": "table",
        "header_paragraphs": header_paragraphs,
        "header_table": table,
        "header_row": first_row,
        "title": title,
        "roles": roles,
        "first_bullet": first_bullet,
    }


def _locate_block(root, company: str):
    return _locate_paragraph_block(root, company) or _locate_table_block(root, company)


def _apply_block(block) -> None:
    _normalize_header_table(block.get("header_table"))

    header_paragraphs = block["header_paragraphs"]
    for paragraph in header_paragraphs:
        _remove_forced_breaks(paragraph)
        _set_zero_left_indent(paragraph)
        _set_flag(paragraph, "keepNext", True)
        _set_flag(paragraph, "keepLines", True)
    if block.get("header_row") is not None:
        _set_row_cant_split(block["header_row"])

    for paragraph in (block["title"], block["roles"]):
        _remove_forced_breaks(paragraph)
        _set_zero_left_indent(paragraph)
        _set_flag(paragraph, "keepNext", True)
        _set_flag(paragraph, "keepLines", True)

    first_bullet = block["first_bullet"]
    _remove_forced_breaks(first_bullet)
    _set_flag(first_bullet, "keepNext", False)
    _set_flag(first_bullet, "keepLines", True)


def _validate_block(block, company: str) -> list[str]:
    reasons = []
    if not block:
        return [f"{company}: employer start block not found"]
    if not _header_table_is_left_aligned(block.get("header_table")):
        reasons.append(f"{company}: company/date table is not left aligned")
    for paragraph in block["header_paragraphs"]:
        if not _has_flag(paragraph, "keepNext"):
            reasons.append(f"{company}: header is not kept with title")
        if not _has_zero_left_indent(paragraph):
            reasons.append(f"{company}: header left alignment does not match title/roles")
    if not _has_flag(block["title"], "keepNext"):
        reasons.append(f"{company}: title/date is not kept with responsibilities")
    if not _has_zero_left_indent(block["title"]):
        reasons.append(f"{company}: title/date left alignment is inconsistent")
    if not _has_flag(block["roles"], "keepNext"):
        reasons.append(f"{company}: responsibilities label is not kept with first bullet")
    if not _has_zero_left_indent(block["roles"]):
        reasons.append(f"{company}: responsibilities left alignment is inconsistent")
    if not _has_flag(block["first_bullet"], "keepLines"):
        reasons.append(f"{company}: first bullet is allowed to split across pages")
    if _has_flag(block["first_bullet"], "keepNext"):
        reasons.append(f"{company}: first bullet incorrectly forces the second bullet to stay with it")
    for paragraph in [*block["header_paragraphs"], block["title"], block["roles"], block["first_bullet"]]:
        if _has_flag(paragraph, "pageBreakBefore"):
            reasons.append(f"{company}: forced page break remains in employer start block")
        if paragraph.xpath(".//w:br[@w:type='page']", namespaces=NS):
            reasons.append(f"{company}: manual page break remains in employer start block")
    return reasons


def _locate_education(root, row):
    body = root.find(".//" + W + "body")
    if body is None:
        return None
    degree = str(row.get("degree") or "").strip()
    school = str(row.get("school") or "").strip()
    children = list(body)
    degree_paragraph = next(
        (child for child in children if child.tag == W + "p" and _text(child) == degree),
        None,
    )
    school_paragraph = next(
        (child for child in children if child.tag == W + "p" and _text(child).startswith(school)),
        None,
    )
    school_table = next(
        (child for child in children if child.tag == W + "tbl" and _text(child).startswith(school)),
        None,
    )
    table_paragraphs = [] if school_table is None else school_table.xpath(".//w:tr[1]/w:tc/w:p", namespaces=NS)
    return {
        "degree": degree_paragraph,
        "school_paragraph": school_paragraph,
        "school_table": school_table,
        "table_paragraphs": table_paragraphs,
    }


def _apply_education_layout(root) -> list[str]:
    reasons = []
    for row in load_master_resume().get("education") or []:
        layout = _locate_education(root, row)
        if not layout or layout["degree"] is None:
            reasons.append("education: degree row not found")
            continue
        degree = layout["degree"]
        _remove_forced_breaks(degree)
        _set_zero_left_indent(degree)
        _set_flag(degree, "keepNext", True)
        _set_flag(degree, "keepLines", True)

        table = layout["school_table"]
        paragraph = layout["school_paragraph"]
        if table is not None:
            _normalize_header_table(table)
            first_row = table.find(".//" + W + "tr")
            if first_row is not None:
                _set_row_cant_split(first_row)
            for item in layout["table_paragraphs"]:
                _remove_forced_breaks(item)
                _set_zero_left_indent(item)
                _set_flag(item, "keepLines", True)
        elif paragraph is not None:
            _remove_forced_breaks(paragraph)
            _set_zero_left_indent(paragraph)
            _set_flag(paragraph, "keepLines", True)
        else:
            reasons.append("education: university/location/date row not found")
    return reasons


def _validate_education_layout(root) -> list[str]:
    reasons = []
    for row in load_master_resume().get("education") or []:
        layout = _locate_education(root, row)
        if not layout or layout["degree"] is None:
            reasons.append("education: degree row not found")
            continue
        if not _has_zero_left_indent(layout["degree"]):
            reasons.append("education: degree left alignment is inconsistent")
        if not _has_flag(layout["degree"], "keepNext"):
            reasons.append("education: degree is not kept with university row")

        table = layout["school_table"]
        paragraph = layout["school_paragraph"]
        if table is not None:
            if not _header_table_is_left_aligned(table):
                reasons.append("education: university/date table is not flush left/full width")
            for item in layout["table_paragraphs"]:
                if not _has_zero_left_indent(item):
                    reasons.append("education: university/date cell alignment is inconsistent")
        elif paragraph is not None:
            if not _has_zero_left_indent(paragraph):
                reasons.append("education: university/location/date left alignment is inconsistent")
        else:
            reasons.append("education: university/location/date row not found")
    return reasons


def _read_root(path: Path):
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read("word/document.xml"))


def _write_root(path: Path, root) -> None:
    xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")
    temp_dir = Path(tempfile.mkdtemp(prefix="resume_pagination_"))
    temp_path = temp_dir / path.name
    try:
        with zipfile.ZipFile(path, "r") as zin, zipfile.ZipFile(temp_path, "w") as zout:
            for info in zin.infolist():
                data = xml if info.filename == "word/document.xml" else zin.read(info.filename)
                zout.writestr(info, data)
        shutil.move(str(temp_path), str(path))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def validate_experience_start_rule(docx_path: str | Path) -> dict:
    path = Path(docx_path)
    if not path.exists() or path.stat().st_size == 0:
        return {"passed": False, "reasons": [f"DOCX missing or empty: {path}"]}
    root = _read_root(path)
    reasons = []
    companies = [row["company"] for row in load_master_resume()["experience"]]
    for company in companies:
        reasons.extend(_validate_block(_locate_block(root, company), company))
    reasons.extend(_validate_education_layout(root))
    return {
        "passed": not reasons,
        "reasons": reasons,
        "policy": "aligned employer header/title/roles plus complete first bullet must start together",
        "education_policy": "degree and university/location share the same left edge; dates remain right aligned",
    }


def enforce_experience_start_rule(docx_path: str | Path) -> dict:
    """Apply the final approved resume alignment and pagination rules.

    Employer company/location, title/date, and Roles & Responsibilities share one
    left edge. An employer may begin on the current page only when that start block
    plus the complete first bullet fit. Later bullets may continue naturally.

    Education is normalized to the same visual system: the degree and university /
    location row share one left edge and any date column remains right aligned.
    """
    path = Path(docx_path)
    if not path.exists() or path.stat().st_size == 0:
        return {"passed": False, "reasons": [f"DOCX missing or empty: {path}"]}
    root = _read_root(path)
    companies = [row["company"] for row in load_master_resume()["experience"]]
    missing = []
    for company in companies:
        block = _locate_block(root, company)
        if block is None:
            missing.append(f"{company}: employer start block not found")
            continue
        _apply_block(block)
    missing.extend(_apply_education_layout(root))
    if missing:
        return {"passed": False, "reasons": missing}
    _write_root(path, root)
    return validate_experience_start_rule(path)
