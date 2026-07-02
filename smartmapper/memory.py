"""Active-learning memory of confirmed mappings.

Every time a human confirms (or corrects) a suggested mapping, the pair is
worth remembering: the next dataset with the same field names should map
instantly with full confidence.  This is the "active learning" component the
schema-matching literature repeatedly highlights as the practical way around
the lack-of-labeled-data problem.  Storage is a plain JSON file so it is easy
to inspect, share across a team, and version-control.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Dict, Optional, Tuple

from .text import normalize


class MappingMemory:
    """Persisted store of ``(source, target) -> confirmation count``."""

    def __init__(self, path: Optional[str] = None):
        self.path = path
        # normalized source -> normalized target -> count
        self._pairs: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        if path and os.path.exists(path):
            self.load()

    def key(self, source: str, target: str) -> Tuple[str, str]:
        return normalize(source), normalize(target)

    def confirm(self, source: str, target: str, weight: int = 1) -> None:
        """Record that ``source`` was confirmed to map to ``target``."""
        s, t = self.key(source, target)
        if not s or not t:
            return
        self._pairs[s][t] += weight

    def prior(self, source: str, target: str) -> float:
        """Learned prior in ``[0, 1]`` that ``source`` maps to ``target``.

        Returns the share of past confirmations of this source that went to
        this specific target, so a field consistently mapped the same way
        earns a strong prior while an ambiguous one stays moderate.
        """
        s, t = self.key(source, target)
        targets = self._pairs.get(s)
        if not targets:
            return 0.0
        total = sum(targets.values())
        return targets.get(t, 0) / total if total else 0.0

    def load(self) -> None:
        with open(self.path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        self._pairs = defaultdict(lambda: defaultdict(int))
        for s, targets in raw.items():
            for t, count in targets.items():
                self._pairs[s][t] = count

    def save(self, path: Optional[str] = None) -> None:
        dest = path or self.path
        if not dest:
            raise ValueError("No path configured for MappingMemory.save()")
        serializable = {s: dict(targets) for s, targets in self._pairs.items()}
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(serializable, fh, indent=2, sort_keys=True)

    def __len__(self) -> int:
        return sum(len(t) for t in self._pairs.values())
