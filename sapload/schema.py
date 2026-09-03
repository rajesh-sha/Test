"""The target schema a template describes, derived rather than configured."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass
class TargetField:
    """One column of an SAP upload template.

    ``name`` is what the rest of the toolkit keys on: the technical field name
    when the template publishes one, otherwise the human label.  Everything
    else is evidence gathered from the template and is allowed to be absent —
    a template that only gives us labels still produces a usable schema.
    """

    name: str
    column: int
    label: str = ""
    technical: str = ""
    mandatory: bool = False
    key: bool = False
    dtype: str = "text"          # text | number | date
    max_length: Optional[int] = None
    allowed: Optional[List[str]] = None
    source_of_truth: List[str] = field(default_factory=list)

    @property
    def required(self) -> bool:
        return self.mandatory or self.key

    def describe(self) -> str:
        bits = [self.dtype]
        if self.max_length:
            bits.append(f"≤{self.max_length}")
        if self.key:
            bits.append("key")
        elif self.mandatory:
            bits.append("mandatory")
        if self.allowed:
            bits.append(f"{len(self.allowed)} allowed values")
        return ", ".join(bits)


@dataclass
class TargetSchema:
    """Everything we learned about a template by reading it."""

    sheet_name: str
    fields: List[TargetField]
    header_rows: int
    label_row: Optional[int] = None
    technical_row: Optional[int] = None
    marker_row: Optional[int] = None
    notes: List[str] = field(default_factory=list)

    @property
    def names(self) -> List[str]:
        return [f.name for f in self.fields]

    @property
    def required_names(self) -> List[str]:
        return [f.name for f in self.fields if f.required]

    @property
    def numeric_columns(self) -> List[int]:
        return [f.column for f in self.fields if f.dtype == "number"]

    def by_name(self, name: str) -> Optional[TargetField]:
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def row_to_cells(self, row: Dict[str, object]) -> List[object]:
        """Lay a mapped record out across the template's actual columns."""
        width = max((f.column for f in self.fields), default=-1) + 1
        cells: List[object] = [""] * width
        for f in self.fields:
            value = row.get(f.name)
            cells[f.column] = "" if value is None else value
        return cells

    def summary(self) -> str:
        req = len(self.required_names)
        helped = sum(1 for f in self.fields if f.allowed)
        return (
            f"{len(self.fields)} fields | {req} required | "
            f"{helped} with value help | data starts at row {self.header_rows + 1}"
        )
