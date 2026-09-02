"""Generate a realistic SAP-style upload template and a ServiceNow-style extract.

The real SAP templates cannot be redistributed, so this builds a stand-in that
carries the same conventions the parser relies on — a sparse group row, a label
row, a mandatory/key marker row, a technical field-name row, a field-length
row, dropdowns on the coded columns and a separate Field List sheet.

The extract is modelled on an FSM sub-contractor claim export: different column
names, different date formats, and a handful of deliberate data problems so the
validation has something real to catch.
"""

from __future__ import annotations

import csv
import os
import random
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

# label, marker, technical name, length, dropdown values
COLUMNS = [
    ("Company Code",   "*k", "CompanyCode",                   4,  ["1000", "2000", "3000"]),
    ("Reference",      "*",  "SupplierInvoiceIDByInvcgParty", 16, None),
    ("Supplier",       "*",  "Supplier",                      10, None),
    ("Invoice Date",   "*",  "DocumentDate",                  10, None),
    ("Posting Date",   "*",  "PostingDate",                   10, None),
    ("Gross Amount",   "*",  "InvoiceGrossAmount",            16, None),
    ("Currency",       "*",  "DocumentCurrency",              3,  ["AUD", "NZD", "USD"]),
    ("Tax Code",       "",   "TaxCode",                       2,  ["P1", "P0", "P2"]),
    ("Cost Centre",    "",   "CostCenter",                    10, None),
    ("G/L Account",    "*",  "GLAccount",                     10, None),
    ("Header Text",    "",   "DocumentHeaderText",            25, None),
    ("Assignment",     "",   "AssignmentReference",           18, None),
]

GROUP_ROW = {0: "Header data", 8: "Account assignment"}


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _col(i: int) -> str:
    out, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def _row(n: int, values) -> str:
    cells = []
    for c, v in enumerate(values):
        if v in (None, ""):
            continue
        cells.append(
            f'<c r="{_col(c)}{n}" t="inlineStr"><is><t xml:space="preserve">'
            f"{_esc(str(v))}</t></is></c>"
        )
    return f'<row r="{n}">{"".join(cells)}</row>'


def _validations() -> str:
    blocks = []
    for i, (_l, _m, _t, _len, allowed) in enumerate(COLUMNS):
        if not allowed:
            continue
        ref = f"{_col(i)}6:{_col(i)}5000"
        blocks.append(
            f'<dataValidation type="list" allowBlank="1" showInputMessage="1" '
            f'showErrorMessage="1" sqref="{ref}">'
            f'<formula1>"{",".join(allowed)}"</formula1></dataValidation>'
        )
    if not blocks:
        return ""
    return f'<dataValidations count="{len(blocks)}">{"".join(blocks)}</dataValidations>'


def _data_sheet() -> str:
    group = [GROUP_ROW.get(i, "") for i in range(len(COLUMNS))]
    rows = "".join([
        _row(1, group),
        _row(2, [c[0] for c in COLUMNS]),
        _row(3, [c[1] for c in COLUMNS]),
        _row(4, [c[2] for c in COLUMNS]),
        _row(5, [c[3] for c in COLUMNS]),
    ])
    cols = "".join(f'<col min="{i+1}" max="{i+1}" width="20" customWidth="1"/>'
                   for i in range(len(COLUMNS)))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<cols>{cols}</cols>"
        f"<sheetData>{rows}</sheetData>"
        f"{_validations()}"
        "</worksheet>"
    )


def _field_list_sheet() -> str:
    rows = [_row(1, ["Field", "Description", "Required", "Length"])]
    for n, (label, marker, tech, length, _a) in enumerate(COLUMNS, start=2):
        req = "Key" if "k" in marker else ("Yes" if "*" in marker else "No")
        rows.append(_row(n, [tech, label, req, length]))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(rows)}</sheetData></worksheet>'
    )


def write_template(path: str) -> None:
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    parts = {
        "[Content_Types].xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>",
        "_rels/.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rel_ns}/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        "xl/workbook.xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'xmlns:r="{rel_ns}"><sheets>'
            '<sheet name="Supplier Invoice" sheetId="1" r:id="rId1"/>'
            '<sheet name="Field List" sheetId="2" r:id="rId2"/>'
            "</sheets></workbook>",
        "xl/_rels/workbook.xml.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rel_ns}/worksheet" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{rel_ns}/worksheet" Target="worksheets/sheet2.xml"/>'
            f'<Relationship Id="rId3" Type="{rel_ns}/styles" Target="styles.xml"/>'
            "</Relationships>",
        "xl/styles.xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
            '<cellXfs count="1"><xf xfId="0"/></cellXfs></styleSheet>',
        "xl/worksheets/sheet1.xml": _data_sheet(),
        "xl/worksheets/sheet2.xml": _field_list_sheet(),
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in parts.items():
            zf.writestr(name, body)


# --------------------------------------------------------------------------- #
# The source extract: an FSM sub-contractor claim export
# --------------------------------------------------------------------------- #
SOURCE_FIELDS = [
    "sys_id", "u_company", "claim_number", "vendor_id", "invoice_dt", "post_dt",
    "gross_amt", "curr", "tax_cd", "cost_centre", "gl_acct", "descr",
    "wo_number", "state",
]


def write_extract(path: str, rows: int = 40, seed: int = 7) -> None:
    rnd = random.Random(seed)
    companies = ["1000", "2000", "3000"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SOURCE_FIELDS)
        w.writeheader()
        for i in range(rows):
            day = 1 + (i % 27)
            rec = {
                "sys_id": f"{rnd.getrandbits(60):015x}",
                "u_company": rnd.choice(companies),
                "claim_number": f"RCTI-2026-{4100 + i}",
                "vendor_id": f"{700000 + rnd.randint(1, 60)}",
                "invoice_dt": f"2026-08-{day:02d}",
                "post_dt": f"2026-09-{day:02d}",
                "gross_amt": f"{rnd.uniform(850, 48000):.2f}",
                "curr": "AUD",
                "tax_cd": rnd.choice(["P1", "P0"]),
                "cost_centre": f"CC{rnd.randint(1000, 1400)}",
                "gl_acct": f"{6000000 + rnd.randint(10, 99)}",
                "descr": f"NBN claim wk{(i % 4) + 31}",
                "wo_number": f"WO{4400000 + i}",
                "state": "Approved",
            }
            # Deliberate defects, so the validation has real work to do.
            if i == 4:
                rec["curr"] = "AU$"                       # not in the dropdown
            if i == 9:
                rec["gl_acct"] = ""                       # mandatory, empty
            if i == 14:
                rec["gross_amt"] = "1,240.00 AUD"         # not a number
            if i == 21:
                rec["descr"] = "NBN sub-contract claim — northern region backlog catch-up"
            if i == 28:
                rec["curr"] = "NZ"                        # not in the dropdown
            w.writerow(rec)


if __name__ == "__main__":
    tpl = os.path.join(HERE, "Supplier Invoice_EN.xlsx")
    src = os.path.join(HERE, "fsm_subcontractor_claims.csv")
    write_template(tpl)
    write_extract(src)
    print(f"wrote {tpl}")
    print(f"wrote {src}")
