"""Minimal, zero-dependency XLSX reader/writer built on the standard library.

An ``.xlsx`` file is a zip of XML parts, so ``zipfile`` plus a little parsing is
all it takes to read one — no ``openpyxl``, no ``pandas``, nothing to install.
That matters here: this toolkit has to run on a locked-down finance laptop with
no package manager, and it has to keep the SAP template it was handed *intact*.

The write path is deliberately surgical.  Rather than rebuild a workbook from
scratch (which would throw away SAP's styling, column widths, dropdowns and
help sheets), we copy the original zip entry-for-entry and swap out only the
``<sheetData>`` element of the one sheet we fill.  Everything SAP shipped in
that file survives the round trip.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

_MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# One <row> element, self-closing or not.
_ROW_RE = re.compile(rb"<row\b[^>]*/>|<row\b[^>]*>.*?</row>", re.DOTALL)
_SHEETDATA_RE = re.compile(rb"<sheetData\b[^>]*/>|<sheetData\b[^>]*>.*?</sheetData>", re.DOTALL)
_CELL_RE = re.compile(rb"<c\b[^>]*/>|<c\b[^>]*>.*?</c>", re.DOTALL)
_ATTR_RE = re.compile(rb'(\w+)="([^"]*)"')
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")


# --------------------------------------------------------------------------- #
# Column reference helpers  (A -> 0, AB -> 27)
# --------------------------------------------------------------------------- #
def _reject_spreadsheetml(path: str) -> None:
    """Fail clearly on an Excel 2003 XML template rather than obscurely.

    Some SAP Migration Cockpit downloads are SpreadsheetML 2003 — plain XML,
    not a zip — even when the browser has named them ``.xlsx``.  Opening one as
    a zip produces a baffling error, so say what actually happened.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(4)
    except OSError:
        return
    if head[:2] == b"PK":
        return
    raise ValueError(
        f"{path} is not an OOXML workbook. SAP sometimes delivers templates as "
        f"Excel 2003 XML (SpreadsheetML), which is plain XML rather than a zip, "
        f"and browsers often save it with an .xlsx extension anyway. Re-download "
        f"the template choosing the XLSX or CSV format, or open it in Excel and "
        f"save as .xlsx."
    )


def col_to_index(ref: str) -> int:
    """``"AB12"`` or ``"AB"`` -> zero-based column index."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def index_to_col(idx: int) -> str:
    """Zero-based column index -> ``"A"``, ``"AB"``, ..."""
    out = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        out = chr(65 + rem) + out
    return out


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
@dataclass
class Validation:
    """A dropdown (``dataValidation type="list"``) found on a sheet.

    SAP ships these on its templates, which makes them the one place a value
    help actually *is* machine-readable — the OData metadata carries none.
    """

    first_col: int
    last_col: int
    values: List[str] = field(default_factory=list)


@dataclass
class Sheet:
    name: str
    path: str
    rows: List[List[str]]
    row_xml: List[bytes]
    cell_styles: Dict[int, Dict[int, str]] = field(default_factory=dict)
    validations: List[Validation] = field(default_factory=list)

    def cell(self, row: int, col: int) -> str:
        if 0 <= row < len(self.rows) and 0 <= col < len(self.rows[row]):
            return self.rows[row][col]
        return ""

    def column_values(self, col: int, start_row: int) -> List[str]:
        return [self.cell(r, col) for r in range(start_row, len(self.rows))]

    def allowed_values_for(self, col: int) -> Optional[List[str]]:
        for v in self.validations:
            if v.first_col <= col <= v.last_col and v.values:
                return v.values
        return None


class Workbook:
    """A read-only view of a workbook, plus the ability to refill one sheet."""

    def __init__(self, path: str):
        self.path = path
        self._shared: List[str] = []
        self.sheets: List[Sheet] = []
        self._raw: Dict[str, bytes] = {}
        self._load()

    # -- loading ----------------------------------------------------------- #
    def _load(self) -> None:
        _reject_spreadsheetml(self.path)
        with zipfile.ZipFile(self.path) as zf:
            self._raw = {n: zf.read(n) for n in zf.namelist()}

        if "xl/sharedStrings.xml" in self._raw:
            self._shared = _parse_shared_strings(self._raw["xl/sharedStrings.xml"])

        rels = _parse_rels(self._raw.get("xl/_rels/workbook.xml.rels", b""))
        for name, rid in _parse_workbook(self._raw.get("xl/workbook.xml", b"")):
            target = rels.get(rid)
            if not target:
                continue
            part = target if target.startswith("xl/") else "xl/" + target.lstrip("/")
            if part not in self._raw:
                continue
            rows, row_xml, styles, vals = _parse_sheet(self._raw[part], self._shared)
            self.sheets.append(
                Sheet(name=name, path=part, rows=rows, row_xml=row_xml,
                      cell_styles=styles, validations=vals)
            )

    def sheet(self, name_or_index) -> Sheet:
        if isinstance(name_or_index, int):
            return self.sheets[name_or_index]
        for s in self.sheets:
            if s.name == name_or_index:
                return s
        raise KeyError(f"no sheet named {name_or_index!r}")

    # -- writing ----------------------------------------------------------- #
    def write_filled(
        self,
        out_path: str,
        sheet: Sheet,
        data_rows: Sequence[Sequence[object]],
        keep_rows: int,
        numeric_cols: Optional[Sequence[int]] = None,
    ) -> None:
        """Copy this workbook to ``out_path``, replacing one sheet's data rows.

        ``keep_rows`` header rows are carried across as their original XML, so
        SAP's own formatting on them is untouched; ``data_rows`` are written
        beneath, reusing the per-column style of the template's first data row
        where the template had one.
        """
        numeric = set(numeric_cols or ())
        style_row = sheet.cell_styles.get(keep_rows, {})

        parts = [b'<sheetData>']
        parts.extend(sheet.row_xml[:keep_rows])
        for offset, values in enumerate(data_rows):
            parts.append(_row_xml(keep_rows + offset + 1, values, style_row, numeric))
        parts.append(b"</sheetData>")
        new_sheetdata = b"".join(parts)

        original = self._raw[sheet.path]
        if not _SHEETDATA_RE.search(original):
            raise ValueError(f"no <sheetData> found in {sheet.path}")
        patched = _SHEETDATA_RE.sub(lambda _m: new_sheetdata, original, count=1)

        with zipfile.ZipFile(self.path) as src, \
                zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                payload = patched if item.filename == sheet.path else src.read(item.filename)
                dst.writestr(item, payload)


def _row_xml(
    row_no: int,
    values: Sequence[object],
    style_row: Dict[int, str],
    numeric_cols: set,
) -> bytes:
    cells: List[str] = []
    for col, value in enumerate(values):
        if value is None or value == "":
            continue
        ref = f"{index_to_col(col)}{row_no}"
        style = style_row.get(col)
        s_attr = f' s="{style}"' if style else ""
        text = str(value)
        if col in numeric_cols and _NUMERIC_RE.match(text.strip()):
            cells.append(f'<c r="{ref}"{s_attr}><v>{text.strip()}</v></c>')
        else:
            cells.append(
                f'<c r="{ref}"{s_attr} t="inlineStr"><is><t xml:space="preserve">'
                f"{_esc(text)}</t></is></c>"
            )
    return f'<row r="{row_no}">{"".join(cells)}</row>'.encode("utf-8")


# --------------------------------------------------------------------------- #
# XML part parsers
# --------------------------------------------------------------------------- #
def _attrs(blob: bytes) -> Dict[str, str]:
    head = blob.split(b">", 1)[0]
    return {k.decode(): v.decode() for k, v in _ATTR_RE.findall(head)}


def _parse_shared_strings(blob: bytes) -> List[str]:
    import xml.etree.ElementTree as ET

    out: List[str] = []
    for si in ET.fromstring(blob).findall(f"{_MAIN_NS}si"):
        # Rich text splits a string across several <t> runs; join them back up.
        out.append("".join(t.text or "" for t in si.iter(f"{_MAIN_NS}t")))
    return out


def _parse_workbook(blob: bytes) -> List[Tuple[str, str]]:
    import xml.etree.ElementTree as ET

    if not blob:
        return []
    root = ET.fromstring(blob)
    out = []
    for sheet in root.iter(f"{_MAIN_NS}sheet"):
        out.append((sheet.get("name", ""), sheet.get(f"{{{_DOC_REL}}}id", "")))
    return out


def _parse_rels(blob: bytes) -> Dict[str, str]:
    import xml.etree.ElementTree as ET

    if not blob:
        return {}
    return {
        r.get("Id", ""): r.get("Target", "")
        for r in ET.fromstring(blob).iter(f"{_REL_NS}Relationship")
    }


def _parse_sheet(blob: bytes, shared: Sequence[str]):
    """Return ``(rows, row_xml, styles, validations)`` for one worksheet part."""
    body = _SHEETDATA_RE.search(blob)
    rows: List[List[str]] = []
    row_xml: List[bytes] = []
    styles: Dict[int, Dict[int, str]] = {}

    if body:
        for r_index, raw_row in enumerate(_ROW_RE.findall(body.group(0))):
            row_xml.append(raw_row)
            values: List[str] = []
            row_styles: Dict[int, str] = {}
            for raw_cell in _CELL_RE.findall(raw_row):
                attrs = _attrs(raw_cell)
                col = col_to_index(attrs.get("r", ""))
                while len(values) <= col:
                    values.append("")
                values[col] = _cell_text(raw_cell, attrs, shared)
                if "s" in attrs:
                    row_styles[col] = attrs["s"]
            rows.append(values)
            if row_styles:
                styles[r_index] = row_styles

    return rows, row_xml, styles, _parse_validations(blob)


def _cell_text(raw_cell: bytes, attrs: Dict[str, str], shared: Sequence[str]) -> str:
    kind = attrs.get("t", "n")
    if kind == "inlineStr":
        m = re.search(rb"<t[^>]*>(.*?)</t>", raw_cell, re.DOTALL)
        return _unescape(m.group(1).decode("utf-8")) if m else ""
    m = re.search(rb"<v>(.*?)</v>", raw_cell, re.DOTALL)
    if not m:
        return ""
    text = _unescape(m.group(1).decode("utf-8"))
    if kind == "s":
        try:
            return shared[int(text)]
        except (ValueError, IndexError):
            return ""
    return text


def _unescape(text: str) -> str:
    return (
        text.replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
    )


def _parse_validations(blob: bytes) -> List[Validation]:
    """Pull inline list dropdowns out of a worksheet.

    Only literal lists (``<formula1>"A,B,C"</formula1>``) are read.  Validations
    that point at a range elsewhere in the workbook are skipped rather than
    guessed at — a wrong value help is worse than none.
    """
    out: List[Validation] = []
    for block in re.findall(rb"<dataValidation\b[^>]*>.*?</dataValidation>|<dataValidation\b[^>]*/>",
                            blob, re.DOTALL):
        attrs = _attrs(block)
        if attrs.get("type") != "list":
            continue
        sqref = attrs.get("sqref", "")
        if not sqref:
            continue
        first_col = last_col = None
        for token in sqref.replace(":", " ").split():
            idx = col_to_index(token)
            if idx < 0:
                continue
            first_col = idx if first_col is None else min(first_col, idx)
            last_col = idx if last_col is None else max(last_col, idx)
        if first_col is None:
            continue
        m = re.search(rb"<formula1[^>]*>(.*?)</formula1>", block, re.DOTALL)
        values: List[str] = []
        if m:
            literal = _unescape(m.group(1).decode("utf-8")).strip()
            if literal.startswith('"') and literal.endswith('"'):
                values = [v.strip() for v in literal[1:-1].split(",") if v.strip()]
        if values:
            out.append(Validation(first_col=first_col, last_col=last_col, values=values))
    return out
