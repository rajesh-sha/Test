"""Transformation detection and application.

A mapping is rarely a straight copy.  ``full_name`` -> ``first_name`` needs a
split; ``01/02/2023`` -> ISO date needs reformatting; ``"YES"`` -> ``True``
needs a boolean cast.  This module proposes a transform for a mapped pair based
on the two column profiles and can apply it to individual values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, List, Optional, Sequence

from .profiling import ColumnProfile
from .text import normalize, tokenize

# Unambiguous formats first.  Ambiguous day/month formats are chosen per
# column via :func:`infer_dayfirst` so a single CSV does not mix calendars.
_UNAMBIGUOUS_DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
    "%d.%m.%Y",  # dotted European — day-first by convention
]

_DAYFIRST_FORMATS = ["%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y"]
_MONTHFIRST_FORMATS = ["%m-%d-%Y", "%m/%d/%Y", "%m/%d/%y"]

_TRUE = {"true", "yes", "y", "t", "1"}
_FALSE = {"false", "no", "n", "f", "0"}


@dataclass
class Transform:
    """A named, reversible-ish value transformation."""

    name: str
    description: str
    apply: Callable[[object], object]


def infer_dayfirst(values: Iterable) -> Optional[bool]:
    """Infer whether slash/dash dates in *values* are day-first.

    Returns ``True`` (D/M), ``False`` (M/D), or ``None`` if the sample does
    not settle the ambiguity.  Any component ``> 12`` is decisive.
    """
    day_evidence = 0
    month_evidence = 0
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$", s)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12 and b <= 12:
            day_evidence += 1
        elif b > 12 and a <= 12:
            month_evidence += 1
    if day_evidence and not month_evidence:
        return True
    if month_evidence and not day_evidence:
        return False
    return None


def _parse_date(s: str, dayfirst: Optional[bool] = None) -> Optional[str]:
    for fmt in _UNAMBIGUOUS_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue

    if dayfirst is True:
        ordered = _DAYFIRST_FORMATS + _MONTHFIRST_FORMATS
    elif dayfirst is False:
        ordered = _MONTHFIRST_FORMATS + _DAYFIRST_FORMATS
    else:
        # No column policy — prefer month-first (common for US CSVs) but still
        # accept the other family as a fallback for individual values.
        ordered = _MONTHFIRST_FORMATS + _DAYFIRST_FORMATS

    for fmt in ordered:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def make_iso_date_transform(dayfirst: Optional[bool] = None) -> Transform:
    """Build a ``to_iso_date`` transform with a fixed day/month policy."""

    def _apply(v: object) -> object:
        s = str(v).strip()
        parsed = _parse_date(s, dayfirst=dayfirst)
        return parsed if parsed is not None else v

    policy = (
        "day-first" if dayfirst is True
        else "month-first" if dayfirst is False
        else "auto"
    )
    return Transform(
        "to_iso_date",
        f"Normalize to ISO-8601 date (YYYY-MM-DD, {policy})",
        _apply,
    )


def _to_iso_date(v: object) -> object:
    """Default date transform (month-first preferred when ambiguous)."""
    return make_iso_date_transform(dayfirst=False).apply(v)


def _to_bool(v: object) -> object:
    s = str(v).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    return v


def _strip_currency(v: object) -> object:
    s = re.sub(r"[^\d.\-]", "", str(v))
    try:
        return float(s)
    except ValueError:
        return v


def _first_token(v: object) -> object:
    parts = str(v).strip().split()
    return parts[0] if parts else v


def _last_token(v: object) -> object:
    parts = str(v).strip().split()
    return parts[-1] if len(parts) > 1 else ("" if not parts else v)


IDENTITY = Transform("identity", "Copy value unchanged", lambda v: v)

_LIBRARY = {
    "to_iso_date": Transform(
        "to_iso_date",
        "Normalize to ISO-8601 date (YYYY-MM-DD, month-first when ambiguous)",
        _to_iso_date,
    ),
    "to_bool": Transform("to_bool", "Coerce yes/no/1/0 to boolean", _to_bool),
    "strip_currency": Transform("strip_currency", "Remove currency symbols -> float", _strip_currency),
    "split_first_name": Transform("split_first_name", "Take first token of full name", _first_token),
    "split_last_name": Transform("split_last_name", "Take last token of full name", _last_token),
    "lowercase": Transform("lowercase", "Lowercase text", lambda v: str(v).lower()),
    "uppercase": Transform("uppercase", "Uppercase text", lambda v: str(v).upper()),
    "trim": Transform("trim", "Strip surrounding whitespace", lambda v: str(v).strip()),
}


def get_transform(name: str) -> Transform:
    return _LIBRARY.get(name, IDENTITY)


def _has_name_token(name: str) -> bool:
    return "name" in tokenize(name)


def _looks_like_full_name(source_name: str, source_profile: Optional[ColumnProfile]) -> bool:
    """True when the source looks like a multi-token full name, not fname/lname."""
    tokens = tokenize(source_name)
    # Already a first/last-name field — do not suggest a split.
    joined = " ".join(tokens)
    if any(t in tokens for t in ("fname", "firstname", "lname", "lastname", "surname", "forename")):
        return False
    if joined in ("first name", "last name", "given name", "family name"):
        return False
    if not _has_name_token(source_name) and "name" not in normalize(source_name).split():
        return False
    if source_profile and source_profile.avg_len and source_profile.avg_len > 8:
        return True
    # Name-only heuristic when no profile: require "full" / multi-word source.
    return "full" in tokens or len(tokens) >= 2


def suggest_transform(
    source_name: str,
    target_name: str,
    source_profile: Optional[ColumnProfile],
    target_profile: Optional[ColumnProfile],
    source_values: Optional[Sequence] = None,
) -> Transform:
    """Pick the most likely transform to convert source values to the target."""
    sp, tp = source_profile, target_profile
    t_tokens = set(tokenize(target_name))
    t_norm_tokens = set(normalize(target_name).split())

    # Full name -> first/last name split (name-driven, values are just text).
    if _looks_like_full_name(source_name, sp):
        if t_tokens & {"first", "given", "fname", "firstname"} or t_norm_tokens & {"first", "given"}:
            return _LIBRARY["split_first_name"]
        if t_tokens & {"last", "surname", "lname", "lastname", "family"} or t_norm_tokens & {"last", "surname", "family"}:
            return _LIBRARY["split_last_name"]

    if tp is None or sp is None:
        return IDENTITY

    # Date normalization when either side already looks like a date.
    if tp.semantic_type in ("date", "datetime") or sp.semantic_type in ("date", "datetime"):
        dayfirst = infer_dayfirst(source_values or ())
        # Default ambiguous US-style CSVs to month-first when undecided.
        return make_iso_date_transform(dayfirst=False if dayfirst is None else dayfirst)

    if tp.semantic_type == "bool":
        return _LIBRARY["to_bool"]

    if tp.semantic_type in ("float", "integer", "currency") and sp.semantic_type == "currency":
        return _LIBRARY["strip_currency"]

    if tp.semantic_type == "email" and sp.semantic_type == "email":
        return _LIBRARY["lowercase"]

    return IDENTITY
