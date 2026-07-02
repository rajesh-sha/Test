"""Value-based column profiling.

Field *names* lie: ``col_7`` and ``phone2`` tell you nothing.  The single
biggest accuracy win in modern schema matching comes from looking at the
*values*.  This module profiles a column of sample values into a compact
signature — inferred semantic type, value patterns, and cardinality — so two
columns can be compared on what they actually contain, not just what they are
called.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set

# Ordered most-specific first: the first pattern that matches the majority of
# non-empty values wins the semantic type.
_TYPE_PATTERNS = [
    ("email", re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")),
    ("uuid", re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)),
    ("url", re.compile(r"^https?://[^\s]+$", re.I)),
    ("ipv4", re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")),
    ("datetime", re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")),
    ("date", re.compile(r"^(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})$")),
    ("phone", re.compile(r"^[+(]?[\d][\d\s().-]{6,}\d$")),
    ("currency", re.compile(r"^[$€£¥]\s?-?\d[\d,]*(\.\d+)?$|^-?\d[\d,]*(\.\d+)?\s?[$€£¥]$")),
    ("bool", re.compile(r"^(true|false|yes|no|y|n|t|f|0|1)$", re.I)),
    ("integer", re.compile(r"^-?\d{1,15}$")),
    ("float", re.compile(r"^-?\d+\.\d+$")),
    ("postal", re.compile(r"^\d{4,6}(-\d{4})?$")),
]


@dataclass
class ColumnProfile:
    """Compact statistical fingerprint of a column's values."""

    semantic_type: str = "unknown"
    non_empty: int = 0
    distinct: int = 0
    min_len: int = 0
    max_len: int = 0
    avg_len: float = 0.0
    numeric: bool = False
    num_min: Optional[float] = None
    num_max: Optional[float] = None
    sample_values: Set[str] = field(default_factory=set)
    from_name: bool = False  # True when inferred from the field name, not data

    @property
    def cardinality_ratio(self) -> float:
        return self.distinct / self.non_empty if self.non_empty else 0.0


def _try_float(v: str) -> Optional[float]:
    try:
        return float(v.replace(",", "").lstrip("$€£¥").rstrip("$€£¥").strip())
    except (ValueError, AttributeError):
        return None


def profile_column(values: Iterable, max_samples: int = 256) -> ColumnProfile:
    """Build a :class:`ColumnProfile` from an iterable of raw cell values."""
    cleaned: List[str] = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s == "":
            continue
        cleaned.append(s)
        if len(cleaned) >= max_samples:
            break

    prof = ColumnProfile()
    if not cleaned:
        return prof

    prof.non_empty = len(cleaned)
    prof.distinct = len(set(cleaned))
    lengths = [len(s) for s in cleaned]
    prof.min_len, prof.max_len = min(lengths), max(lengths)
    prof.avg_len = sum(lengths) / len(lengths)
    prof.sample_values = {s.lower() for s in cleaned[:64]}

    # Numeric range (helps distinguish e.g. age vs year vs price).
    nums = [n for n in (_try_float(s) for s in cleaned) if n is not None]
    if len(nums) >= max(1, int(0.9 * len(cleaned))):
        prof.numeric = True
        prof.num_min, prof.num_max = min(nums), max(nums)

    # Majority-vote semantic type.
    prof.semantic_type = _infer_type(cleaned)
    return prof


# Keyword -> expected semantic type, used when a field has no sample values and
# we must fall back to the name alone.  Longer/more-specific keys first.
_NAME_TYPE_HINTS = [
    ("email", "email"), ("e mail", "email"),
    ("phone", "phone"), ("mobile", "phone"), ("cell", "phone"), ("tel", "phone"),
    ("dob", "date"), ("birth", "date"), ("date", "date"), ("created", "date"),
    ("updated", "date"), ("timestamp", "datetime"),
    ("zip", "postal"), ("postal", "postal"), ("postcode", "postal"),
    ("uuid", "uuid"), ("guid", "uuid"),
    ("price", "currency"), ("amount", "currency"), ("cost", "currency"),
    ("spend", "currency"), ("revenue", "currency"), ("balance", "currency"),
    ("url", "url"), ("website", "url"),
]


def type_hint_from_name(name: str) -> str:
    """Best-guess semantic type inferred from a field name (no data needed)."""
    from .text import normalize
    norm = normalize(name)
    tokens = set(norm.split())
    for keyword, type_name in _NAME_TYPE_HINTS:
        if keyword in tokens or keyword in norm:
            return type_name
    return "unknown"


def profile_from_name(name: str) -> ColumnProfile:
    """Synthesize a values-free profile from a field name.

    Used when one side of a match has no sample rows: we still know roughly
    what *kind* of value the field should hold, which is enough for the value
    signal to disambiguate (e.g. a source column of emails vs a target field
    literally named ``email``).
    """
    prof = ColumnProfile(semantic_type=type_hint_from_name(name), from_name=True)
    prof.non_empty = 1  # sentinel: not an empty column, just no captured values
    return prof


def _infer_type(values: List[str]) -> str:
    threshold = 0.8 * len(values)
    for type_name, pattern in _TYPE_PATTERNS:
        hits = sum(1 for v in values if pattern.match(v))
        if hits >= threshold:
            return type_name
    # Low-cardinality short strings look categorical/enum.
    distinct = len(set(v.lower() for v in values))
    if distinct <= max(2, len(values) * 0.1) and distinct <= 30:
        return "categorical"
    return "text"


def profile_similarity(a: ColumnProfile, b: ColumnProfile) -> float:
    """Similarity in ``[0, 1]`` between two column profiles.

    Combines three signals: matching semantic type (strongest), overlapping
    numeric range, and Jaccard overlap of actual sample values (catches shared
    enums / code lists / foreign keys even when names differ completely).
    """
    if a.non_empty == 0 or b.non_empty == 0:
        return 0.0

    score = 0.0

    # Semantic type agreement.  A shared *distinctive* type (email, phone,
    # date, uuid, ...) is strong evidence; a shared generic "text" type barely
    # counts because almost everything is text.
    if a.semantic_type == b.semantic_type and a.semantic_type != "unknown":
        score += 0.25 if a.semantic_type in ("text", "categorical") else 0.8

    # Direct value overlap — the strongest possible evidence.
    if a.sample_values and b.sample_values:
        overlap = len(a.sample_values & b.sample_values) / len(
            a.sample_values | b.sample_values
        )
        score += 0.45 * overlap

    # Numeric range overlap.
    if a.numeric and b.numeric and None not in (a.num_min, a.num_max, b.num_min, b.num_max):
        lo = max(a.num_min, b.num_min)
        hi = min(a.num_max, b.num_max)
        span_a = (a.num_max - a.num_min) or 1.0
        span_b = (b.num_max - b.num_min) or 1.0
        if hi >= lo:
            score += 0.2 * (hi - lo) / max(span_a, span_b)

    # Similar cardinality profile (both keys, or both enums) — only meaningful
    # when both sides carry real sampled values.
    if a.sample_values and b.sample_values and abs(
        a.cardinality_ratio - b.cardinality_ratio
    ) < 0.1:
        score += 0.05

    return min(1.0, score)
