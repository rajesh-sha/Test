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
from typing import Callable, Optional

from .profiling import ColumnProfile

_DATE_INPUT_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y",
    "%m-%d-%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S", "%m/%d/%y", "%d/%m/%y",
]

_TRUE = {"true", "yes", "y", "t", "1"}
_FALSE = {"false", "no", "n", "f", "0"}


@dataclass
class Transform:
    """A named, reversible-ish value transformation."""

    name: str
    description: str
    apply: Callable[[object], object]


def _to_iso_date(v: object) -> object:
    s = str(v).strip()
    for fmt in _DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return v


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
    "to_iso_date": Transform("to_iso_date", "Normalize to ISO-8601 date (YYYY-MM-DD)", _to_iso_date),
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


def suggest_transform(
    source_name: str,
    target_name: str,
    source_profile: Optional[ColumnProfile],
    target_profile: Optional[ColumnProfile],
) -> Transform:
    """Pick the most likely transform to convert source values to the target."""
    sp, tp = source_profile, target_profile
    s_norm, t_norm = source_name.lower(), target_name.lower()

    # Full name -> first/last name split (name-driven, values are just text).
    if "name" in s_norm and ("first" in t_norm or "given" in t_norm or "fname" in t_norm):
        if sp and sp.avg_len and sp.avg_len > 3:
            return _LIBRARY["split_first_name"]
    if "name" in s_norm and ("last" in t_norm or "surname" in t_norm or "lname" in t_norm):
        if sp and sp.avg_len and sp.avg_len > 3:
            return _LIBRARY["split_last_name"]

    if tp is None or sp is None:
        return IDENTITY

    # Date normalization when either side already looks like a date.
    if tp.semantic_type in ("date", "datetime") or sp.semantic_type in ("date", "datetime"):
        return _LIBRARY["to_iso_date"]

    if tp.semantic_type == "bool":
        return _LIBRARY["to_bool"]

    if tp.semantic_type in ("float", "integer", "currency") and sp.semantic_type == "currency":
        return _LIBRARY["strip_currency"]

    if tp.semantic_type == "email" and sp.semantic_type == "email":
        return _LIBRARY["lowercase"]

    return IDENTITY
