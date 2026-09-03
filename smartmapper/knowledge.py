"""Built-in domain knowledge: synonyms and abbreviations.

Pure lexical similarity never learns that ``dob`` means ``date of birth`` or
that ``zip`` and ``postal_code`` are the same thing.  This module encodes that
common business-data vocabulary so the matcher can bridge the semantic gap
without a heavyweight embedding model.  It is intentionally editable — teams
extend :data:`SYNONYM_GROUPS` with their own house vocabulary.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List

# Each inner list is a set of terms that mean the same thing.  Order does not
# matter; every term maps to a shared canonical concept id.
SYNONYM_GROUPS: List[List[str]] = [
    ["id", "identifier", "key", "pk", "uid", "uuid", "guid"],
    ["email", "e mail", "mail", "email address", "emailaddr"],
    ["phone", "telephone", "tel", "mobile", "cell", "msisdn", "contact number"],
    ["name", "full name", "fullname"],
    ["first name", "given name", "forename", "fname", "firstname"],
    ["last name", "surname", "family name", "lname", "lastname"],
    ["dob", "date of birth", "birth date", "birthday", "born"],
    ["address", "addr", "street address", "street"],
    ["city", "town", "municipality"],
    ["state", "province", "region"],
    ["zip", "zipcode", "zip code", "postal code", "postcode", "post code"],
    ["country", "nation", "country code"],
    ["qty", "quantity", "count", "number of", "num", "amount of items"],
    ["price", "cost", "unit price", "rate"],
    ["amount", "amt", "total", "sum", "value"],
    ["currency", "ccy", "curr"],
    ["created", "created at", "creation date", "date created", "inserted"],
    ["updated", "updated at", "modified", "last modified", "modification date"],
    ["status", "state", "stage"],
    ["company", "organization", "org", "employer", "business"],
    ["title", "job title", "position", "role"],
    ["description", "desc", "details", "notes", "comment", "remarks"],
    ["gender", "sex"],
    ["age", "years old"],
    ["latitude", "lat"],
    ["longitude", "lng", "lon", "long"],
    ["username", "user name", "login", "handle", "screen name"],
    ["password", "pwd", "pass", "secret"],
    ["customer", "client", "account", "user", "member"],
    ["product", "item", "sku", "article", "goods"],
    ["order", "purchase", "transaction", "sale"],
    ["invoice", "bill", "receipt"],
    ["discount", "rebate", "markdown"],
    ["tax", "vat", "gst"],
    ["active", "enabled", "is active"],
]


def _build_index() -> Dict[str, int]:
    index: Dict[str, int] = {}
    for concept_id, group in enumerate(SYNONYM_GROUPS):
        for term in group:
            index[term] = concept_id
    return index


# term -> concept id
_TERM_TO_CONCEPT: Dict[str, int] = _build_index()


def register_synonyms(groups: List[List[str]]) -> None:
    """Teach the matcher a domain vocabulary at runtime.

    Each inner list is a set of terms that mean the same thing.  Calling this
    is how a caller layers house or industry vocabulary (SAP field names, say)
    on top of the built-in general business terms without editing this file.
    Registering the same group twice is harmless.
    """
    global _TERM_TO_CONCEPT
    known = {tuple(sorted(g)) for g in SYNONYM_GROUPS}
    for group in groups:
        if tuple(sorted(group)) in known:
            continue
        SYNONYM_GROUPS.append(list(group))
    _TERM_TO_CONCEPT = _build_index()
    cache_clear = getattr(concepts_in, "cache_clear", None)
    if cache_clear is not None:      # concepts_in may be memoized
        cache_clear()


def concept_of(term: str) -> int:
    """Concept id for a normalized term, or ``-1`` if unknown."""
    return _TERM_TO_CONCEPT.get(term.strip().lower(), -1)


def concepts_in(normalized_name: str) -> FrozenSet[int]:
    """All known concepts referenced by a normalized field name.

    Matches multi-word terms (e.g. ``"date of birth"``) as well as single
    tokens, so both ``"dob"`` and ``"date_of_birth"`` resolve to the same
    concept id.
    """
    found = set()
    # Whole-phrase hit (handles "date of birth", "postal code", ...).
    whole = concept_of(normalized_name)
    if whole >= 0:
        found.add(whole)
    tokens = normalized_name.split()
    # Single tokens.
    for tok in tokens:
        c = concept_of(tok)
        if c >= 0:
            found.add(c)
    # Adjacent bigrams (handles "zip code", "first name", ...).
    for i in range(len(tokens) - 1):
        c = concept_of(f"{tokens[i]} {tokens[i + 1]}")
        if c >= 0:
            found.add(c)
    return frozenset(found)


def synonym_score(name_a: str, name_b: str) -> float:
    """1.0 if the two normalized names share a known concept, else 0.0."""
    ca, cb = concepts_in(name_a), concepts_in(name_b)
    return 1.0 if ca & cb else 0.0
