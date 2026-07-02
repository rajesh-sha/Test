"""String-similarity primitives used by the ensemble matcher.

Pure-Python, zero-dependency implementations of the metrics that the schema
matching literature consistently finds most useful for comparing attribute
labels: edit distance (Levenshtein), Jaro-Winkler (rewards common prefixes,
great for abbreviations), token Jaccard, and Monge-Elkan (best-token pairing
between two token lists).  All functions return a score in ``[0.0, 1.0]``
where ``1.0`` means identical.
"""

from __future__ import annotations

from typing import Sequence


def levenshtein(a: str, b: str) -> int:
    """Classic edit distance (insertions, deletions, substitutions)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def levenshtein_ratio(a: str, b: str) -> float:
    """Normalized edit similarity in ``[0, 1]``."""
    if not a and not b:
        return 1.0
    longest = max(len(a), len(b))
    return 1.0 - levenshtein(a, b) / longest if longest else 1.0


def jaro(a: str, b: str) -> float:
    """Jaro similarity."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    match_dist = max(len(a), len(b)) // 2 - 1
    match_dist = max(match_dist, 0)
    a_matches = [False] * len(a)
    b_matches = [False] * len(b)
    matches = 0
    for i, ca in enumerate(a):
        lo = max(0, i - match_dist)
        hi = min(i + match_dist + 1, len(b))
        for j in range(lo, hi):
            if not b_matches[j] and ca == b[j]:
                a_matches[i] = b_matches[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    # Count transpositions.
    transpositions = 0
    k = 0
    for i, matched in enumerate(a_matches):
        if matched:
            while not b_matches[k]:
                k += 1
            if a[i] != b[k]:
                transpositions += 1
            k += 1
    transpositions //= 2
    return (
        matches / len(a)
        + matches / len(b)
        + (matches - transpositions) / matches
    ) / 3.0


def jaro_winkler(a: str, b: str, prefix_weight: float = 0.1) -> float:
    """Jaro-Winkler: Jaro boosted by shared leading characters.

    Especially strong for abbreviations like ``qty`` vs ``quantity`` where a
    long shared prefix signals a real relationship.
    """
    base = jaro(a, b)
    prefix = 0
    for ca, cb in zip(a, b):
        if ca == cb:
            prefix += 1
        else:
            break
        if prefix == 4:
            break
    return base + prefix * prefix_weight * (1 - base)


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    """Set overlap of two token collections."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def monge_elkan(a: Sequence[str], b: Sequence[str], inner=jaro_winkler) -> float:
    """Monge-Elkan: average best-match similarity between token lists.

    For each token in ``a`` take its best match in ``b`` under ``inner`` and
    average.  Handles reordered / partially-overlapping multi-word names such
    as ``"home phone number"`` vs ``"phone (home)"`` better than raw Jaccard.
    """
    if not a or not b:
        return 0.0
    total = 0.0
    for ta in a:
        total += max(inner(ta, tb) for tb in b)
    return total / len(a)


def symmetric_monge_elkan(a: Sequence[str], b: Sequence[str], inner=jaro_winkler) -> float:
    """Order-independent Monge-Elkan (average of both directions)."""
    return (monge_elkan(a, b, inner) + monge_elkan(b, a, inner)) / 2.0
