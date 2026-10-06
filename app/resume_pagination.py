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
    """Make employer header/title/roles share one exact left edge."""
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


def _normalize_header_table(table) -> None:
    """Remove table centering/cell padding that can visually offset company rows."""
    if table is None:
        return
    tblpr = table.find(W + "tblPr")
    if tblpr is None:
        tblpr = etree.Element(W + "tblPr")
        table.insert(0, tblpr)

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
    for side in ("left", "right"):
        node = tbl_cell_mar.find(W + side)
        if node is None:
            node = etree.SubElement(tbl_cell_mar, W + side)
        node.set(W + "type", "dxa")
        node.set(W + "w", "0")

    for cell in table.xpath(".//w:tr[1]/w:tc", namespaces=NS):
        tcpr = cell.find(W + "tcPr")
        if tcpr is None:
            tcpr = etree.Element(W + "tcPr")
            cell.insert(0, tcpr)
        tcmar = tcpr.find(W + "tcMar")
        if tcmar is None:
            tcmar = etree.SubElement(tcpr, W + "tcMar")
        for side in ("left", "right"):
            node = tcmar.find(W + side)
            if node is None:
                node = etree.SubElement(tcmar, W + side)
            node.set(W + "type", "dxa")
            node.set(W + "w", "0")


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
    return {
        "passed": not reasons,
        "reasons": reasons,
        "policy": "aligned employer header/title/roles plus complete first bullet must start together",
    }


def enforce_experience_start_rule(docx_path: str | Path) -> dict:
    """Normalize employer alignment and prevent orphaned employer starts.

    Company/location, title/date, and Roles & Responsibilities are normalized to
    the same left edge. Word/LibreOffice may begin an employer on the current page
    only when that start block and the complete first bullet fit there. Otherwise
    the start block moves to the next page. Later bullets remain free to continue
    on following pages.
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
    if missing:
        return {"passed": False, "reasons": missing}
    _write_root(path, root)
    return validate_experience_start_rule(path)
