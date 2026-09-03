"""Build the reconciliation pack that turns a load into an auditable control.

SAP delivers no source-to-target reconciliation, and on the Service Stream
integration slide three of the four flows end with "SAP report to reconcile
load to FSM".  This module produces the source half of that: what was
extracted, what was mapped, what was written, and the control totals to agree
against once SAP has posted.

Nothing here is clever.  It is deliberately the kind of artefact an auditor can
read without explanation, which is the only kind that is worth producing.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .schema import TargetSchema
from .validate import ValidationReport


@dataclass
class ControlTotal:
    field: str
    count: int
    total: float

    def line(self) -> str:
        return f"{self.field:<28} {self.count:>8,}  {self.total:>18,.2f}"


@dataclass
class ReconPack:
    run_id: str
    generated: str
    source_name: str
    template_name: str
    source_rows: int
    mapped_rows: int
    written_rows: int
    coverage: float
    unmapped_targets: List[str]
    unused_sources: List[str]
    totals: List[ControlTotal]
    validation: Optional[ValidationReport] = None
    notes: List[str] = field(default_factory=list)

    def as_text(self) -> str:
        w = 74
        out = [
            "=" * w,
            "  LOAD RECONCILIATION PACK",
            "=" * w,
            f"  Run ID        {self.run_id}",
            f"  Generated     {self.generated}",
            f"  Source        {self.source_name}",
            f"  Template      {self.template_name}",
            "",
            "-" * w,
            "  RECORD COUNTS",
            "-" * w,
            f"  Extracted from source                {self.source_rows:>10,}",
            f"  Mapped to the template schema        {self.mapped_rows:>10,}",
            f"  Written to the upload file           {self.written_rows:>10,}",
        ]
        gap = self.source_rows - self.written_rows
        out.append(
            f"  Difference                           {gap:>10,}"
            + ("   <-- INVESTIGATE" if gap else "   (nil — reconciles)")
        )

        if self.totals:
            out += ["", "-" * w, "  CONTROL TOTALS  (agree these to SAP after posting)",
                    "-" * w,
                    f"  {'Field':<28} {'Count':>8}  {'Total':>18}"]
            out += [f"  {t.line()}" for t in self.totals]

        out += ["", "-" * w, "  MAPPING COVERAGE", "-" * w,
                f"  Template fields matched              {self.coverage:>9.0%}"]
        if self.unmapped_targets:
            out.append(f"  Template fields with no source ({len(self.unmapped_targets)}):")
            out += [f"      - {n}" for n in self.unmapped_targets[:15]]
            if len(self.unmapped_targets) > 15:
                out.append(f"      … {len(self.unmapped_targets) - 15} more")
        if self.unused_sources:
            out.append(f"  Source columns not used ({len(self.unused_sources)}):")
            out += [f"      - {n}" for n in self.unused_sources[:15]]

        if self.validation:
            out += ["", "-" * w, "  VALIDATION", "-" * w,
                    f"  {self.validation.summary()}"]
            if self.validation.issues:
                out.append("")
                out += [f"  {line}" for line in self.validation.top()]

        if self.notes:
            out += ["", "-" * w, "  NOTES", "-" * w]
            out += [f"  - {n}" for n in self.notes]

        out += ["", "=" * w,
                "  Sign-off:  prepared by ______________   reviewed by ______________",
                "=" * w]
        return "\n".join(out)


def build_recon(
    source_name: str,
    template_name: str,
    schema: TargetSchema,
    source_rows: Sequence[dict],
    mapped_rows: Sequence[dict],
    written_rows: Sequence[dict],
    plan_coverage: float,
    unmapped_targets: Sequence[str],
    unused_sources: Sequence[str],
    validation: Optional[ValidationReport] = None,
    notes: Optional[Sequence[str]] = None,
) -> ReconPack:
    """Assemble the pack, computing a control total for every numeric field."""
    totals: List[ControlTotal] = []
    for f in schema.fields:
        if f.dtype != "number":
            continue
        count = 0
        total = 0.0
        for row in written_rows:
            raw = row.get(f.name)
            if raw is None or str(raw).strip() == "":
                continue
            try:
                total += float(str(raw).replace(",", "").strip())
                count += 1
            except ValueError:
                continue
        if count:
            totals.append(ControlTotal(field=f.name, count=count, total=total))

    digest = hashlib.sha256(
        f"{source_name}|{len(source_rows)}|{len(written_rows)}".encode()
    ).hexdigest()[:12]

    return ReconPack(
        run_id=digest,
        generated=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source_name=source_name,
        template_name=template_name,
        source_rows=len(source_rows),
        mapped_rows=len(mapped_rows),
        written_rows=len(written_rows),
        coverage=plan_coverage,
        unmapped_targets=list(unmapped_targets),
        unused_sources=list(unused_sources),
        totals=totals,
        validation=validation,
        notes=list(notes or []),
    )
