"""High-level SmartFieldMapper API.

This is the front door.  Give it two schemas (just field names, or field names
plus sample rows) and it returns a reviewable :class:`MappingPlan`: for every
target field, the best source field, a confidence score, the reasons, and a
suggested transform.  Confirm the plan and :meth:`connect` streams a source
dataset through it to produce data in the target schema — the "100x" payoff is
that the tedious part (finding and wiring the mapping) is done for you.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .matcher import Candidate, rank_sources_for_target, resolve_assignment
from .memory import MappingMemory
from .profiling import ColumnProfile, profile_column, profile_from_name
from .transforms import IDENTITY, Transform, suggest_transform


@dataclass
class FieldMapping:
    """One resolved target<-source link plus how to transform it."""

    target: str
    source: Optional[str]
    confidence: float
    transform: Transform
    reasons: List[str] = field(default_factory=list)
    alternatives: List[Candidate] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.source is None:
            return "unmatched"
        if self.confidence >= 0.85:
            return "auto"          # safe to apply without review
        if self.confidence >= 0.5:
            return "review"        # likely right, glance at it
        return "low"               # a guess, needs a human


@dataclass
class MappingPlan:
    """The full, reviewable mapping between two schemas."""

    mappings: List[FieldMapping]
    unmatched_sources: List[str]

    def as_dict(self) -> Dict[str, Optional[str]]:
        """Simple ``target -> source`` dict of the resolved links."""
        return {m.target: m.source for m in self.mappings}

    @property
    def coverage(self) -> float:
        matched = sum(1 for m in self.mappings if m.source is not None)
        return matched / len(self.mappings) if self.mappings else 0.0

    def summary(self) -> str:
        auto = sum(1 for m in self.mappings if m.status == "auto")
        review = sum(1 for m in self.mappings if m.status == "review")
        low = sum(1 for m in self.mappings if m.status == "low")
        unmatched = sum(1 for m in self.mappings if m.source is None)
        return (
            f"{len(self.mappings)} target fields | "
            f"{auto} auto, {review} review, {low} low-confidence, "
            f"{unmatched} unmatched | coverage {self.coverage:.0%}"
        )


class SmartFieldMapper:
    """Ensemble field mapper with optional value profiling and memory."""

    def __init__(self, memory: Optional[MappingMemory] = None):
        self.memory = memory

    # ------------------------------------------------------------------ #
    # Profiling helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _profiles_from_rows(
        fields: Sequence[str], rows: Optional[Sequence[dict]]
    ) -> Dict[str, ColumnProfile]:
        """Profile each field from real values, falling back to a name hint.

        Fields with sampled values get a full data-driven profile; fields
        without (no rows supplied, or all-empty column) get a lightweight
        profile inferred from the field name so the value signal still helps.
        """
        columns: Dict[str, list] = {f: [] for f in fields}
        for row in rows or []:
            for f in fields:
                columns[f].append(row.get(f))
        profiles: Dict[str, ColumnProfile] = {}
        for f in fields:
            prof = profile_column(columns[f])
            profiles[f] = prof if prof.non_empty else profile_from_name(f)
        return profiles

    @staticmethod
    def _column_values(
        field: str, rows: Optional[Sequence[dict]]
    ) -> List[object]:
        if not rows:
            return []
        return [row.get(field) for row in rows]

    # ------------------------------------------------------------------ #
    # Mapping
    # ------------------------------------------------------------------ #
    def map_schema(
        self,
        source_fields: Sequence[str],
        target_fields: Sequence[str],
        source_rows: Optional[Sequence[dict]] = None,
        target_rows: Optional[Sequence[dict]] = None,
        threshold: float = 0.35,
    ) -> MappingPlan:
        """Produce a :class:`MappingPlan` mapping source fields to target fields."""
        source_fields = list(source_fields)
        target_fields = list(target_fields)
        src_profiles = self._profiles_from_rows(source_fields, source_rows)
        tgt_profiles = self._profiles_from_rows(target_fields, target_rows)

        assignment = resolve_assignment(
            source_fields, target_fields,
            src_profiles, tgt_profiles,
            memory=self.memory, threshold=threshold,
        )
        by_target = {c.target: c for c in assignment}
        matched_sources = {c.source for c in assignment}

        mappings: List[FieldMapping] = []
        for tgt in target_fields:
            cand = by_target.get(tgt)
            alts = rank_sources_for_target(
                tgt, source_fields, tgt_profiles.get(tgt),
                src_profiles, self.memory, top_k=3,
            )
            if cand is None:
                # No confident 1:1 link — still surface the best few guesses.
                mappings.append(FieldMapping(
                    target=tgt, source=None, confidence=0.0,
                    transform=IDENTITY,
                    reasons=["no confident match above threshold"],
                    alternatives=alts,
                ))
                continue

            transform = suggest_transform(
                cand.source, tgt,
                src_profiles.get(cand.source), tgt_profiles.get(tgt),
                source_values=self._column_values(cand.source, source_rows),
            )
            mappings.append(FieldMapping(
                target=tgt, source=cand.source, confidence=cand.score,
                transform=transform, reasons=cand.reasons, alternatives=alts,
            ))

        unmatched_sources = [s for s in source_fields if s not in matched_sources]
        return MappingPlan(mappings=mappings, unmatched_sources=unmatched_sources)

    # ------------------------------------------------------------------ #
    # Connecting: apply a plan to real data
    # ------------------------------------------------------------------ #
    def connect(
        self, plan: MappingPlan, source_rows: Sequence[dict]
    ) -> List[dict]:
        """Stream source rows through a confirmed plan into the target schema.

        This is the payoff step: every source record is rewritten into a target
        record, applying the suggested per-field transform as it goes.
        """
        out: List[dict] = []
        for row in source_rows:
            new_row: Dict[str, object] = {}
            for m in plan.mappings:
                if m.source is None:
                    new_row[m.target] = None
                    continue
                raw = row.get(m.source)
                if raw is None or (isinstance(raw, str) and raw.strip() == ""):
                    new_row[m.target] = None
                    continue
                new_row[m.target] = m.transform.apply(raw)
            out.append(new_row)
        return out

    def learn(
        self,
        plan: MappingPlan,
        *,
        min_status: str = "auto",
    ) -> int:
        """Feed confirmed mappings back into memory (active learning).

        By default only ``auto``-tier mappings are learned, so review/low
        guesses are not reinforced.  Pass ``min_status="review"`` (or
        ``"low"``) to also learn lower-confidence pairs after human review.

        Returns the number of pairs confirmed.
        """
        if self.memory is None:
            return 0
        rank = {"auto": 3, "review": 2, "low": 1, "unmatched": 0}
        min_rank = rank.get(min_status, 3)
        learned = 0
        for m in plan.mappings:
            if m.source is None:
                continue
            if rank.get(m.status, 0) >= min_rank:
                self.memory.confirm(m.source, m.target)
                learned += 1
        return learned


# ---------------------------------------------------------------------- #
# Convenience CSV loaders
# ---------------------------------------------------------------------- #
def read_csv(path: str) -> tuple[List[str], List[dict]]:
    """Read a CSV into ``(fieldnames, rows)``."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    return fields, rows


def write_csv(path: str, fields: Sequence[str], rows: Sequence[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=list(fields), extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
