import io
import zipfile

from app import company_feeders


def _xlsx_bytes():
    shared="""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="4" uniqueCount="4">
  <si><t>CU_NUMBER</t></si><si><t>CU_NAME</t></si>
  <si><t>12345</t></si><si><t>Example Credit Union</t></si>
</sst>"""
    sheet="""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
  <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
  <row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c></row>
</sheetData></worksheet>"""
    inner=io.BytesIO()
    with zipfile.ZipFile(inner,"w") as z:
        z.writestr("xl/sharedStrings.xml",shared)
        z.writestr("xl/worksheets/sheet1.xml",sheet)
    outer=io.BytesIO()
    with zipfile.ZipFile(outer,"w") as z:
        z.writestr("active-credit-unions.xlsx",inner.getvalue())
    return outer.getvalue()


class _Response:
    def __init__(self,payload):self.payload=payload
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):return self.payload


def test_ncua_active_credit_union_feeder_parses_latest_official_list(monkeypatch):
    html=b'<a href="/files/publications/analysis/federally-insured-credit-union-list-june-2026.zip">List</a>'
    payload=_xlsx_bytes()
    def fake_urlopen(req,timeout=30):
        url=getattr(req,"full_url",str(req))
        return _Response(payload if url.endswith(".zip") else html)
    monkeypatch.setattr(company_feeders,"urlopen",fake_urlopen)
    rows=company_feeders.ncua_active_credit_unions()
    assert rows==[{
        "company":"Example Credit Union",
        "ncua_charter":"12345",
        "discovered_by":"ncua_active_federally_insured_credit_unions",
    }]


def test_ncua_feeder_is_enabled_by_default():
    assert company_feeders.FEEDERS["ncua_active_credit_unions"] is company_feeders.ncua_active_credit_unions

# Regression guard: feeder registry must remain importable and enabled in CI.

