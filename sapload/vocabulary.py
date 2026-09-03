"""Domain vocabulary, loaded from data rather than written in code.

Everything the matcher knows about SAP field names lives in ``knowledge.json``
next to this file — one file, read by both the Python toolkit and the browser
build, so there is nothing to keep in step by hand.

Adding a client's own terms is an edit to that file. No Python changes, no
JavaScript changes, no rebuild of anything but the single-file workbench.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List

from smartmapper.knowledge import register_synonyms

KNOWLEDGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "knowledge.json")

_loaded: Dict = {}
_registered = False


def knowledge() -> Dict:
    """The shared knowledge file, read once."""
    global _loaded
    if not _loaded:
        with open(KNOWLEDGE_PATH, encoding="utf-8") as fh:
            _loaded = json.load(fh)
    return _loaded


def synonym_groups() -> List[List[str]]:
    return knowledge().get("synonyms", [])


def thresholds() -> Dict[str, float]:
    return knowledge().get("thresholds", {})


def install() -> None:
    """Register the vocabulary with the matcher. Safe to call repeatedly."""
    global _registered
    if _registered:
        return
    register_synonyms(synonym_groups())
    _registered = True


def extend(groups: List[List[str]]) -> None:
    """Add house vocabulary on top, for a term that is not worth a file edit."""
    install()
    register_synonyms(groups)


def reload() -> None:
    """Pick up an edit to knowledge.json without restarting."""
    global _loaded, _registered
    _loaded, _registered = {}, False
    install()


# Kept for callers that imported the old constant.
SAP_SYNONYM_GROUPS = synonym_groups()
