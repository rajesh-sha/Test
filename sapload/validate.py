"""Validate mapped rows against the schema the template described.

Every rule here is *derived*, never written by hand: if the template marks a
column mandatory, we check it is filled; if it publishes a length, we check it;
if it carries a dropdown, we check membership.  Add a column to the template
and it is validated on the next run with no code change.

The point is to fail on the desk, not in SAP.  Eight hundred supplier invoices
rejected at row 400 is an operational incident; the same eight hundred rejected
here is a five-minute fix before anyone uploads anything.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .schema import TargetSchema

_NUM_RE = re.compile(r"^-?[\d,]*\.?\d+$")
_DATE_FORMATS = (
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{2}[./]\d{2}[./]\d{4}$"),
    re.compile(r"^\d{8}$"),
)


@dataclass
class Issue:
    row: int                 # 1-based index into the data rows, as a user counts
    field: str
    severity: str            # "error" blocks the upload; "warning" does not
    message: str
    value: str = ""

    def __str__(self) -> str:
        shown = f" (got {self.value!r})" if self.value else ""
        return f"row {self.row} · {self.field}: {self.message}{shown}"


@dataclass
class ValidationReport:
    issues: List[Issue]
    row_count: int

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def bad_rows(self) -> set:
        return {i.row for i in self.errors}

    @property
    def clean_row_count(self) -> int:
        return self.row_count - len(self.bad_rows)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return (
            f"{self.row_count} rows | {self.clean_row_count} clean, "
            f"{len(self.bad_rows)} with errors | "
            f"{len(self.errors)} errors, {len(self.warnings)} warnings"
        )

    def top(self, limit: int = 12) -> List[str]:
        """The most common problems first — fixing one usually fixes hundreds."""
        counts: Dict[str, List[Issue]] = {}
        for issue in self.issues:
            counts.setdefault(f"{issue.field}: {issue.message}", []).append(issue)
        ranked = sorted(counts.items(), key=lambda kv: -len(kv[1]))
        lines = []
        for text, group in ranked[:limit]:
            rows = ", ".join(str(i.row) for i in group[:3])
            more = f" +{len(group) - 3} more" if len(group) > 3 else ""
            lines.append(f"[{len(group):>4}x] {text}  (rows {rows}{more})")
        return lines


def validate(schema: TargetSchema, rows: Sequence[Dict[str, object]]) -> ValidationReport:
    """Check every mapped row against the derived schema."""
    issues: List[Issue] = []

    for idx, row in enumerate(rows, start=1):
        for field in schema.fields:
            raw = row.get(field.name)
            text = "" if raw is None else str(raw).strip()

            if not text:
                if field.required:
                    issues.append(Issue(idx, field.name, "error",
                                        "required by the template but empty"))
                continue

            if field.max_length and len(text) > field.max_length:
                issues.append(Issue(idx, field.name, "error",
                                    f"longer than the template allows "
                                    f"({len(text)} > {field.max_length})", text[:40]))

            if field.dtype == "number" and not _NUM_RE.match(text.replace(" ", "")):
                issues.append(Issue(idx, field.name, "error",
                                    "expected a number", text[:40]))

            if field.dtype == "date" and not any(p.match(text) for p in _DATE_FORMATS):
                issues.append(Issue(idx, field.name, "warning",
                                    "does not look like a date SAP will accept",
                                    text[:40]))

            if field.allowed and text not in field.allowed:
                # Offer the correction rather than just the rejection: a bad
                # code is nearly always a near-miss of a good one, and naming
                # it turns a defect list into a fix list.
                near = difflib.get_close_matches(text, field.allowed, n=1, cutoff=0.5)
                if near:
                    detail = f"not an allowed value — did you mean {near[0]!r}?"
                else:
                    shown = ", ".join(field.allowed[:5])
                    detail = (f"not one of the template's allowed values "
                              f"({shown}{'…' if len(field.allowed) > 5 else ''})")
                issues.append(Issue(idx, field.name, "error", detail, text[:40]))

    return ValidationReport(issues=issues, row_count=len(rows))
