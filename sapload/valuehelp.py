"""Live value help, pulled from the read APIs the tenant already exposes.

The template's dropdowns are the free version of this and they cover only the
handful of columns SAP bothered to constrain.  A read-only connection covers
the rest: a wrong cost centre or a closed G/L account is then caught on the
operator's desk instead of by SAP halfway through an upload.

Read-only by construction — every entity here is a GET, and the client refuses
writes unless a run explicitly enabled them.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .sapclient import S4Client, SapError

# field-name pattern -> (service path, key property, optional text property)
# Matched against the template's technical name, then its label.  Ordered:
# the first pattern that matches wins, so the specific ones come first.
def _catalogue():
    """(pattern, service, key, text) tuples, from the shared knowledge file.

    Ordered: the first pattern that matches a field wins, so the specific
    entries come before the general ones. Edit knowledge.json to add a service.
    """
    from .vocabulary import knowledge
    return [(e["match"], e["service"], e["key"], e.get("text"))
            for e in knowledge().get("value_help", [])]


CATALOGUE = _catalogue()
CACHE_TTL = 12 * 3600      # reference data changes slowly; a day is too long


@dataclass
class ValueSet:
    field: str
    entity: str
    values: List[str] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)
    fetched: float = 0.0
    truncated: bool = False

    def describe(self) -> str:
        return (f"{self.field}: {len(self.values):,} value(s) from "
                f"{self.entity.rsplit('/', 1)[-1]}"
                + (" (truncated)" if self.truncated else ""))


def catalogue_entry(field_name: str, label: str = "") -> Optional[tuple]:
    """Which read API, if any, covers this template field."""
    for candidate in (field_name, label):
        if not candidate:
            continue
        needle = candidate.strip().lower()
        for pattern, path, key, text in CATALOGUE:
            if re.search(pattern, needle):
                return path, key, text
    return None


def fetch_value_help(
    client: S4Client,
    schema,
    cache_path: Optional[str] = None,
    limit: int = 5000,
) -> Dict[str, ValueSet]:
    """Pull allowed values for every template field the catalogue recognises.

    A field the tenant will not let us read is skipped with a note rather than
    treated as an error: partial value help is useful, and a missing
    authorisation for one entity should not stop the run.
    """
    cache = _load_cache(cache_path)
    out: Dict[str, ValueSet] = {}

    for tf in schema.fields:
        if tf.allowed:
            continue                       # the template already told us
        entry = catalogue_entry(tf.technical or tf.name, tf.label)
        if not entry:
            continue
        path, key, text = entry

        cached = cache.get(tf.name)
        if cached and time.time() - cached.get("fetched", 0) < CACHE_TTL:
            out[tf.name] = ValueSet(field=tf.name, entity=path,
                                    values=cached["values"], labels=cached.get("labels", {}),
                                    fetched=cached["fetched"],
                                    truncated=cached.get("truncated", False))
            continue

        select = key if not text else f"{key},{text}"
        try:
            rows = client.get_all(path, {"$select": select}, page=500, cap=limit)
        except SapError:
            continue                       # not authorised or not activated

        values, labels = [], {}
        for row in rows:
            code = str(row.get(key, "")).strip()
            if not code:
                continue
            values.append(code)
            if text and row.get(text):
                labels[code] = str(row[text])
        vs = ValueSet(field=tf.name, entity=path, values=sorted(set(values)),
                      labels=labels, fetched=time.time(),
                      truncated=len(rows) >= limit)
        out[tf.name] = vs

    _save_cache(cache_path, out)
    return out


def apply_value_help(schema, value_sets: Dict[str, ValueSet]) -> List[str]:
    """Attach fetched values to the schema so validation checks them too."""
    notes = []
    for name, vs in value_sets.items():
        tf = schema.by_name(name)
        if not tf or not vs.values:
            continue
        tf.allowed = vs.values
        notes.append(f"Value help for {name} came from SAP ({len(vs.values):,} values).")
        if vs.truncated:
            notes.append(f"{name} has more values than were read; a valid value "
                         f"could be reported as invalid. Narrow the selection.")
    return notes


def _load_cache(path: Optional[str]) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_cache(path: Optional[str], sets: Dict[str, ValueSet]) -> None:
    if not path or not sets:
        return
    payload = _load_cache(path)
    for name, vs in sets.items():
        payload[name] = {"values": vs.values, "labels": vs.labels,
                         "fetched": vs.fetched, "truncated": vs.truncated}
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    except OSError:
        pass
