"""Built-in domain knowledge: synonyms and abbreviations.

Pure lexical similarity never learns that ``dob`` means ``date of birth`` or
that ``zip`` and ``postal_code`` are the same thing.  This module encodes that
common business-data vocabulary so the matcher can bridge the semantic gap
without a heavyweight embedding model.  It is intentionally editable — teams
extend :data:`SYNONYM_GROUPS` with their own house vocabulary, then call
:func:`rebuild_index`.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Set

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
    # Geographic subdivision only — do NOT also put "state" under status.
    ["state", "province", "region"],
    ["zip", "zipcode", "zip code", "postal code", "postcode", "post code"],
    ["country", "nation", "country code"],
    ["qty", "quantity", "count", "number of", "num", "amount of items"],
    ["price", "cost", "unit price", "rate"],
    ["amount", "amt", "total", "sum", "value", "spend", "lifetime value", "ltv"],
    ["currency", "ccy", "curr"],
    ["created", "created at", "creation date", "date created", "inserted", "signup", "signup date"],
    ["updated", "updated at", "modified", "last modified", "modification date"],
    # Status/workflow — intentionally excludes "state" (geographic).
    ["status", "stage", "workflow status"],
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

# Concepts that describe *what kind of thing* a field is about (entity /
# subject).  Sharing only these — e.g. customer_email vs user_phone — is not
# enough to call two fields synonyms.
_ENTITY_GROUP_TERMS = {
    "customer", "client", "account", "user", "member",
    "product", "item", "sku", "article", "goods",
    "order", "purchase", "transaction", "sale",
    "invoice", "bill", "receipt",
    "company", "organization", "org", "employer", "business",
}


def _build_index() -> tuple[Dict[str, int], Set[int]]:
    index: Dict[str, int] = {}
    entity_ids: Set[int] = set()
    for concept_id, group in enumerate(SYNONYM_GROUPS):
        is_entity = False
        for term in group:
            index[term] = concept_id
            if term in _ENTITY_GROUP_TERMS:
                is_entity = True
        if is_entity:
            entity_ids.add(concept_id)
    return index, entity_ids


# term -> concept id; concept ids that are entity/subject concepts
_TERM_TO_CONCEPT: Dict[str, int]
_ENTITY_CONCEPTS: Set[int]


def rebuild_index() -> None:
    """Rebuild the term→concept index after editing :data:`SYNONYM_GROUPS`."""
    global _TERM_TO_CONCEPT, _ENTITY_CONCEPTS
    _TERM_TO_CONCEPT, _ENTITY_CONCEPTS = _build_index()


rebuild_index()


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
    # Adjacent bigrams / trigrams (handles "zip code", "first name",
    # "lifetime value", ...).
    for n in (2, 3):
        for i in range(len(tokens) - n + 1):
            c = concept_of(" ".join(tokens[i : i + n]))
            if c >= 0:
                found.add(c)
    return frozenset(found)


def synonym_score(name_a: str, name_b: str) -> float:
    """Soft synonym score in ``[0, 1]`` for two normalized field names.

    Sharing only an entity/subject concept (customer, order, product, …) is
    not enough — ``customer_email`` must not score as a synonym of
    ``user_phone``.  Attribute concepts must overlap, and the score is the
    overlap coefficient of the non-entity concept sets (falling back to
    entity overlap when neither side carries an attribute concept).
    """
    ca, cb = concepts_in(name_a), concepts_in(name_b)
    if not ca or not cb:
        return 0.0

    attr_a = ca - _ENTITY_CONCEPTS
    attr_b = cb - _ENTITY_CONCEPTS

    # Prefer attribute overlap when either side has an attribute concept.
    # Use the overlap coefficient (|∩| / min) so a short alias like ``fname``
    # still scores 1.0 against ``first name`` even if the longer side also
    # picks up a generic ``name`` token concept.
    if attr_a or attr_b:
        inter = attr_a & attr_b
        if not inter:
            return 0.0
        return len(inter) / min(len(attr_a), len(attr_b))

    # Both sides are pure entity labels (rare) — allow entity overlap.
    inter = ca & cb
    if not inter:
        return 0.0
    return len(inter) / min(len(ca), len(cb))
