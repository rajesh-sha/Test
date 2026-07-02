"""Field-name normalization and tokenization.

Field names arrive in wildly inconsistent shapes: ``customerEmailAddress``,
``customer_email_addr``, ``Cust. E-Mail``, ``EMAIL_2``.  Before any two names
can be compared meaningfully they have to be reduced to a canonical form and
split into semantic tokens.  Everything in the matcher builds on the two
functions here.
"""

from __future__ import annotations

import re
from typing import List

# Tokens that carry no discriminating meaning in a field name.  They are
# dropped during tokenization so ``customer_id`` and ``the customer id`` match.
_STOPWORDS = {
    "the", "a", "an", "of", "for", "to", "in", "on", "at", "by",
    "col", "column", "field", "value", "val", "data", "info",
}

# Splits camelCase / PascalCase while keeping acronym runs together, e.g.
# ``customerID`` -> ``customer ID`` and ``HTTPStatus`` -> ``HTTP Status``.
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_ALNUM_RE = re.compile(r"[^0-9a-zA-Z]+")
_DIGIT_BOUNDARY_RE = re.compile(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])")


def normalize(name: str) -> str:
    """Return a lowercase, space-collapsed canonical form of ``name``.

    ``"Customer  E-Mail Address"`` and ``"customerEmailAddress"`` both
    normalize to ``"customer email address"``.
    """
    if name is None:
        return ""
    text = _CAMEL_RE.sub(" ", str(name))
    text = _DIGIT_BOUNDARY_RE.sub(" ", text)
    text = _NON_ALNUM_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def tokenize(name: str, drop_stopwords: bool = True) -> List[str]:
    """Split a field name into normalized semantic tokens.

    ``"customerEmailAddr"`` -> ``["customer", "email", "addr"]``.
    """
    tokens = normalize(name).split()
    if drop_stopwords:
        tokens = [t for t in tokens if t not in _STOPWORDS]
    return tokens


def token_set(name: str, drop_stopwords: bool = True) -> frozenset:
    """Tokens as a set, convenient for Jaccard-style comparisons."""
    return frozenset(tokenize(name, drop_stopwords=drop_stopwords))
