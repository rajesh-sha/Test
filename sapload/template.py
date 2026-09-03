"""Read an SAP upload template and work out, unaided, what it wants.

This is the piece that makes the toolkit dynamic.  Nothing here is configured
per object: hand it ``JournalEntry_Template.xlsx`` or ``Supplier Invoice_EN.xlsx``
or next release's replacement, and it works out for itself where the header
block ends, which row carries the technical field names, which cells mark a
field mandatory, and what values each column will accept.

The heuristics lean on conventions SAP actually uses — a label row above a
technical-name row, ``*`` for mandatory and ``k`` for key, dropdowns for coded
fields — but none of them is required.  A template that offers only labels
still yields a usable schema; it just yields a less opinionated one.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .schema import TargetField, TargetSchema
from .xlsx import Sheet, Workbook

_MARKER_RE = re.compile(r"^[*+kK]{1,3}$")
_IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,}$")
_INT_RE = re.compile(r"^\d{1,4}$")
_DATE_HINT = re.compile(r"date|dat$|_dt$|posting|document date", re.I)
_NUM_HINT = re.compile(r"amount|amt|qty|quantity|value|price|rate|percent|total", re.I)

# Sheets SAP ships alongside the data sheet that we must not mistake for it.
_NON_DATA_SHEET = re.compile(
    r"field\s*list|introduction|instructions|help|read\s*me|notes|legend|"
    r"documentation|cover|about",
    re.I,
)

MAX_HEADER_SCAN = 8


# --------------------------------------------------------------------------- #
# Row classification
# --------------------------------------------------------------------------- #
def _row_stats(values: Sequence[str]) -> Dict[str, float]:
    filled = [v.strip() for v in values if v and v.strip()]
    if not filled:
        return {"fill": 0.0, "marker": 0.0, "ident": 0.0, "integer": 0.0, "avg_len": 0.0}
    n = len(filled)
    return {
        "fill": n / max(len(values), 1),
        "marker": sum(1 for v in filled if _MARKER_RE.match(v)) / n,
        "ident": sum(1 for v in filled if _IDENT_RE.match(v) and " " not in v) / n,
        "integer": sum(1 for v in filled if _INT_RE.match(v)) / n,
        "avg_len": sum(len(v) for v in filled) / n,
    }


def _classify_header(sheet: Sheet) -> Dict[str, Optional[int]]:
    """Decide which of the leading rows are label / technical / marker / length.

    Rows are scored independently and then assigned greedily by how
    characteristic they are, so a template can carry any subset of them in any
    order without the caller knowing.
    """
    scan = min(MAX_HEADER_SCAN, len(sheet.rows))
    stats = [_row_stats(sheet.rows[r]) for r in range(scan)]

    marker_row = _best(stats, "marker", 0.30)
    length_row = _best(stats, "integer", 0.60, exclude={marker_row})
    technical_row = _best(stats, "ident", 0.55, exclude={marker_row, length_row},
                          prefer_last=True)

    # The label row is the wordiest remaining row — human captions are longer
    # and contain spaces, unlike technical names.
    label_row = None
    best_len = 0.0
    for r, st in enumerate(stats):
        if r in {marker_row, length_row, technical_row} or st["fill"] < 0.3:
            continue
        if st["avg_len"] > best_len:
            best_len, label_row = st["avg_len"], r

    known = [r for r in (label_row, technical_row, marker_row, length_row) if r is not None]
    header_rows = max(known) + 1 if known else 1

    # A template may leave a blank spacer row between the header block and the
    # first data row; treat it as part of the header.
    while header_rows < len(sheet.rows) and not any(
        v.strip() for v in sheet.rows[header_rows]
    ):
        header_rows += 1

    return {
        "label": label_row,
        "technical": technical_row,
        "marker": marker_row,
        "length": length_row,
        "header_rows": header_rows,
    }


def _best(
    stats: Sequence[Dict[str, float]],
    key: str,
    threshold: float,
    exclude: Optional[set] = None,
    prefer_last: bool = False,
) -> Optional[int]:
    exclude = {e for e in (exclude or set()) if e is not None}
    best_idx, best_val = None, threshold
    order = range(len(stats) - 1, -1, -1) if prefer_last else range(len(stats))
    for r in order:
        if r in exclude or stats[r]["fill"] < 0.3:
            continue
        if stats[r][key] > best_val or (prefer_last and stats[r][key] >= best_val
                                        and best_idx is None):
            best_idx, best_val = r, stats[r][key]
    return best_idx


# --------------------------------------------------------------------------- #
# Type inference
# --------------------------------------------------------------------------- #
def _infer_dtype(name: str, samples: Sequence[str]) -> str:
    """Prefer the evidence in the data; fall back to what the name implies."""
    real = [s.strip() for s in samples if s and s.strip()]
    if real:
        numeric = sum(1 for s in real if re.match(r"^-?[\d,]+(\.\d+)?$", s))
        dated = sum(1 for s in real if re.match(r"^\d{4}-\d{2}-\d{2}|^\d{2}[./]\d{2}[./]\d{4}", s))
        if dated / len(real) > 0.7:
            return "date"
        if numeric / len(real) > 0.7:
            return "number"
    if _DATE_HINT.search(name):
        return "date"
    if _NUM_HINT.search(name):
        return "number"
    return "text"


def _pick_data_sheet(wb: Workbook) -> Sheet:
    """The data sheet is the widest one that isn't an instructions sheet."""
    candidates = [s for s in wb.sheets if not _NON_DATA_SHEET.search(s.name)]
    if not candidates:
        candidates = list(wb.sheets)
    if not candidates:
        raise ValueError("workbook has no sheets")
    return max(candidates, key=lambda s: max((len(r) for r in s.rows[:MAX_HEADER_SCAN]),
                                             default=0))


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def read_template(path: str, sheet_name: Optional[str] = None) -> Tuple[TargetSchema, Workbook, Sheet]:
    """Derive a :class:`TargetSchema` from an SAP upload template.

    Returns the schema together with the open workbook and sheet, so the caller
    can write a filled copy back without re-reading the file.
    """
    wb = Workbook(path)
    sheet = wb.sheet(sheet_name) if sheet_name else _pick_data_sheet(wb)
    layout = _classify_header(sheet)
    header_rows = layout["header_rows"] or 1

    width = max((len(r) for r in sheet.rows[:header_rows] or [[]]), default=0)
    notes: List[str] = []
    fields: List[TargetField] = []

    for col in range(width):
        label = _at(sheet, layout["label"], col)
        technical = _at(sheet, layout["technical"], col)
        marker = _at(sheet, layout["marker"], col)
        length = _at(sheet, layout["length"], col)

        name = technical or label
        if not name.strip():
            continue

        evidence = []
        if technical:
            evidence.append("technical name row")
        if label:
            evidence.append("label row")

        mandatory = "*" in marker or "+" in marker
        key = "k" in marker.lower()
        if marker:
            evidence.append("marker row")

        allowed = sheet.allowed_values_for(col)
        if allowed:
            evidence.append("template dropdown")

        samples = sheet.column_values(col, header_rows)
        dtype = _infer_dtype(name, samples)
        max_length = int(length) if _INT_RE.match(length or "") else None

        fields.append(TargetField(
            name=name.strip(), column=col, label=label.strip(),
            technical=technical.strip(), mandatory=mandatory, key=key,
            dtype=dtype, max_length=max_length, allowed=allowed,
            source_of_truth=evidence,
        ))

    if layout["technical"] is None:
        notes.append(
            "No technical-name row detected — mapping onto the visible labels. "
            "Check the filled file before uploading."
        )
    if layout["marker"] is None:
        notes.append(
            "No mandatory/key marker row detected — required-field checks are "
            "limited to what the data itself reveals."
        )
    if not any(f.allowed for f in fields):
        notes.append("Template carries no dropdowns, so no value help was harvested.")

    schema = TargetSchema(
        sheet_name=sheet.name, fields=fields, header_rows=header_rows,
        label_row=layout["label"], technical_row=layout["technical"],
        marker_row=layout["marker"], notes=notes,
    )
    return schema, wb, sheet


def _at(sheet: Sheet, row: Optional[int], col: int) -> str:
    return "" if row is None else sheet.cell(row, col).strip()
