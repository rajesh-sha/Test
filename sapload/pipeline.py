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
import re
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

_NUMERIC = re.compile(r"^-?[\d,]*\.?\d+$")


@dataclass
class LoadResult:
    schema: TargetSchema
    plan: MappingPlan
    validation: ValidationReport
    recon: ReconPack
    output_paths: List[str]
    rows_written: int

    @property
    def output_path(self) -> Optional[str]:
        return self.output_paths[0] if self.output_paths else None


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
    max_rows: Optional[int] = None,
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
    output_paths: List[str] = []
    if output_path:
        cells = [schema.row_to_cells(r) for r in rows_to_write]
        # The upload apps have hard per-file ceilings — F2548 takes at most 999
        # journal entries, and the supplier invoice app is reportedly lower.
        # Splitting here is far cheaper than discovering the limit at row 800.
        for index, batch in enumerate(_chunk(cells, max_rows), start=1):
            path = output_path if len(cells) <= (max_rows or len(cells) or 1) \
                else _numbered(output_path, index)
            wb.write_filled(
                out_path=path, sheet=sheet, data_rows=batch,
                keep_rows=schema.header_rows, numeric_cols=schema.numeric_columns,
            )
            output_paths.append(path)
            written += len(batch)
        if len(output_paths) > 1:
            notes.append(
                f"Split into {len(output_paths)} files of at most {max_rows:,} "
                f"rows to stay inside the upload app's per-file limit."
            )

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
        output_paths=output_paths, rows_written=written or len(rows_to_write),
    )


def _inadmissible(field, source: str, rows: Sequence[dict]) -> Optional[str]:
    """Return why this source column cannot fill this field, or None if it can.

    Judged on the data, not the name.  A column of free text cannot fill a
    numeric field however closely it is named, and a column whose values never
    appear in the template's dropdown is not that field.
    """
    values = [str(r.get(source, "")).strip() for r in rows]
    values = [v for v in values if v]
    if not values:
        return None

    sample = values[:200]
    if field.dtype == "number":
        numeric = sum(1 for v in sample if _NUMERIC.match(v.replace(",", "")))
        if numeric / len(sample) < 0.5:
            return f"{source!r} holds text, but this field takes a number"

    if field.allowed:
        permitted = {a.casefold() for a in field.allowed}
        hits = sum(1 for v in sample if v.casefold() in permitted)
        if hits == 0:
            return (f"no value in {source!r} appears in the template's list "
                    f"for this field")

    if field.max_length:
        over = sum(1 for v in sample if len(v) > field.max_length)
        if over / len(sample) > 0.9:
            return (f"nearly every value in {source!r} exceeds this field's "
                    f"{field.max_length}-character limit")
    return None


def _chunk(rows: List, size: Optional[int]) -> List[List]:
    if not size or size <= 0 or len(rows) <= size:
        return [rows]
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def _numbered(path: str, index: int) -> str:
    stem, ext = os.path.splitext(path)
    return f"{stem}_{index:02d}{ext}"


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

    # Drop matches the data cannot support, before letting confidence decide.
    # A high-scoring name match onto a column whose values could never be
    # accepted is worse than no match: it looks right in the review and fails
    # in SAP.  Filtering the hypothesis space first is a bigger accuracy lever
    # than any amount of extra scoring.
    for _c, idx, winner, _alias in best:
        if winner.source is None:
            continue
        reason = _inadmissible(schema.fields[idx], winner.source, source_rows)
        if reason:
            winner.source = None
            winner.confidence = 0.0
            winner.reasons = [reason]

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
