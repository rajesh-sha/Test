"""End to end: a source extract in, a filled SAP template and a recon pack out.

    extract  ->  derive schema from the template
             ->  auto-map with smartmapper (confidence-scored, learns)
             ->  validate against the derived rules
             ->  write the filled template, formatting intact
             ->  produce the reconciliation pack

No step needs a connection to SAP, which is the whole point: the tool can run
anywhere, and the only thing that touches the production system is a person
uploading a file they have already seen validated.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from smartmapper import (
    FieldMapping, MappingMemory, MappingPlan, SmartFieldMapper, read_csv,
)

from . import vocabulary

from .recon import ReconPack, build_recon
from .schema import TargetSchema
from .template import read_template
from .validate import ValidationReport, validate
from .xlsx import Workbook


@dataclass
class LoadResult:
    schema: TargetSchema
    plan: MappingPlan
    validation: ValidationReport
    recon: ReconPack
    output_path: Optional[str]
    rows_written: int


def read_source(path: str) -> Tuple[List[str], List[dict]]:
    """Read a source extract from CSV or XLSX (first sheet, first row = header)."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        wb = Workbook(path)
        sheet = wb.sheets[0]
        if not sheet.rows:
            return [], []
        header = [h.strip() for h in sheet.rows[0]]
        rows = []
        for values in sheet.rows[1:]:
            if not any(v.strip() for v in values):
                continue
            rows.append({
                name: (values[i] if i < len(values) else "")
                for i, name in enumerate(header) if name
            })
        return [h for h in header if h], rows
    return read_csv(path)


def load(
    source_path: str,
    template_path: str,
    output_path: Optional[str] = None,
    memory_path: Optional[str] = None,
    sheet_name: Optional[str] = None,
    only_clean: bool = False,
    threshold: float = 0.35,
    learn_threshold: float = 0.85,
    overrides: Optional[Dict[str, str]] = None,
) -> LoadResult:
    """Run the whole pipeline.

    ``overrides`` lets a reviewer pin ``target -> source`` links the matcher got
    wrong; those choices are remembered, so the correction only has to be made
    once per template.  Everything else is remembered only if it scored at or
    above ``learn_threshold`` — see the note where memory is written.
    """
    schema, wb, sheet = read_template(template_path, sheet_name=sheet_name)
    source_fields, source_rows = read_source(source_path)

    vocabulary.install()
    memory = MappingMemory(memory_path) if memory_path else None
    mapper = SmartFieldMapper(memory=memory)
    plan, winning_alias = map_with_aliases(
        mapper, schema, source_fields, source_rows, threshold=threshold
    )
    if overrides:
        _apply_overrides(plan, overrides, source_fields)

    mapped_rows = mapper.connect(plan, source_rows)
    report = validate(schema, mapped_rows)

    rows_to_write = mapped_rows
    notes: List[str] = list(schema.notes)
    if only_clean and report.bad_rows:
        rows_to_write = [r for i, r in enumerate(mapped_rows, start=1)
                         if i not in report.bad_rows]
        notes.append(
            f"{len(report.bad_rows)} row(s) with errors were held back from the "
            f"upload file at the caller's request."
        )

    written = 0
    if output_path:
        cells = [schema.row_to_cells(r) for r in rows_to_write]
        wb.write_filled(
            out_path=output_path, sheet=sheet, data_rows=cells,
            keep_rows=schema.header_rows, numeric_cols=schema.numeric_columns,
        )
        written = len(cells)

    recon = build_recon(
        source_name=os.path.basename(source_path),
        template_name=os.path.basename(template_path),
        schema=schema,
        source_rows=source_rows,
        mapped_rows=mapped_rows,
        written_rows=rows_to_write,
        plan_coverage=plan.coverage,
        unmapped_targets=[m.target for m in plan.mappings if m.source is None],
        unused_sources=plan.unmatched_sources,
        validation=report,
        notes=notes,
    )

    if memory is not None:
        # Only remember what a human would stand behind.  Learning an
        # unreviewed 60%-confidence guess is how a tool like this quietly
        # entrenches a wrong mapping: the guess becomes a prior, the prior
        # raises the score, and by run three nobody questions it.  So we
        # remember reviewer overrides always, and otherwise only matches that
        # were already strong enough to apply without review.
        confirmed = set(overrides or ())
        for m in plan.mappings:
            if m.source is None:
                continue
            if m.target not in confirmed and m.confidence < learn_threshold:
                continue
            memory.confirm(m.source, m.target)
            alias = winning_alias.get(m.target)
            if alias and alias != m.target:
                memory.confirm(m.source, alias)
        memory.save()

    return LoadResult(
        schema=schema, plan=plan, validation=report, recon=recon,
        output_path=output_path if written else None,
        rows_written=written or len(rows_to_write),
    )


def _apply_overrides(
    plan: MappingPlan, overrides: Dict[str, str], source_fields: Sequence[str]
) -> None:
    known = set(source_fields)
    for mapping in plan.mappings:
        if mapping.target not in overrides:
            continue
        chosen = overrides[mapping.target]
        if chosen and chosen not in known:
            raise ValueError(
                f"override for {mapping.target!r} names {chosen!r}, which is not "
                f"a column in the source extract"
            )
        mapping.source = chosen or None
        mapping.confidence = 1.0 if chosen else 0.0
        mapping.reasons = ["confirmed by reviewer"]


# --------------------------------------------------------------------------- #
# Alias-aware matching
# --------------------------------------------------------------------------- #
def map_with_aliases(
    mapper: SmartFieldMapper,
    schema: TargetSchema,
    source_fields: Sequence[str],
    source_rows: Sequence[dict],
    threshold: float = 0.35,
) -> Tuple[MappingPlan, Dict[str, str]]:
    """Match against both names a template gives each field, and keep the better.

    An SAP template publishes a technical name (``GLAccount``) and a human label
    ("G/L Account").  A source extract might resemble either — ``gl_acct`` is
    much closer to the label, ``GLAccount`` to the technical name.  Matching
    once against each and keeping whichever scored higher costs one extra pass
    and recovers fields that a single-name match drops entirely.

    Returns the merged plan and, for each target, the alias that won — so the
    mapping memory can be keyed on the name that actually did the work.
    """
    technical = [f.technical or f.name for f in schema.fields]
    labels = [f.label or f.technical or f.name for f in schema.fields]

    plans = [mapper.map_schema(source_fields, technical, source_rows,
                               threshold=threshold)]
    if labels != technical:
        plans.append(mapper.map_schema(source_fields, labels, source_rows,
                                       threshold=threshold))

    # Pick the better of the two candidates for each field, by index.
    best: List[Tuple[float, int, FieldMapping, str]] = []
    for idx, field in enumerate(schema.fields):
        winner, alias = None, field.name
        for plan, names in zip(plans, (technical, labels)):
            candidate = plan.mappings[idx]
            if candidate.source is None:
                continue
            # ``>=`` matters: the label pass runs second, so on a tie the
            # human label wins.  That is deliberate.  A long compound technical
            # name like ``SupplierInvoiceIDByInvcgParty`` shares generic tokens
            # ("id", "by", "party") with unrelated source columns and scores
            # spuriously; the label ("Reference") matches on meaning instead.
            if winner is None or candidate.confidence >= winner.confidence:
                winner, alias = candidate, names[idx]
        if winner is None:
            winner = plans[0].mappings[idx]
        best.append((winner.confidence, idx, winner, alias))

    # Two fields may now want the same source column; the more confident wins.
    taken: Dict[str, int] = {}
    for confidence, idx, winner, _alias in sorted(best, key=lambda b: -b[0]):
        if winner.source is None:
            continue
        if winner.source in taken:
            winner.source = None
            winner.confidence = 0.0
            winner.reasons = ["source column already claimed by a stronger match"]
        else:
            taken[winner.source] = idx

    mappings: List[FieldMapping] = []
    winning_alias: Dict[str, str] = {}
    for _c, idx, winner, alias in sorted(best, key=lambda b: b[1]):
        field = schema.fields[idx]
        mappings.append(FieldMapping(
            target=field.name, source=winner.source, confidence=winner.confidence,
            transform=winner.transform, reasons=winner.reasons,
            alternatives=winner.alternatives,
        ))
        if winner.source is not None:
            winning_alias[field.name] = alias

    unused = [s for s in source_fields if s not in taken]
    return MappingPlan(mappings=mappings, unmatched_sources=unused), winning_alias
