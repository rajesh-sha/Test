"""The ensemble matcher — where the intelligence lives.

No single signal is reliable on its own: names are inconsistent, values are
sometimes absent, and synonyms only cover known vocabulary.  The matcher scores
every source/target field pair on *all* available signals, blends them into one
calibrated confidence, and then resolves a globally consistent one-to-one
assignment.  Each score carries a human-readable explanation so a reviewer can
see *why* two fields were matched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import knowledge, similarity
from .memory import MappingMemory
from .profiling import ColumnProfile, profile_similarity
from .text import normalize, tokenize


@dataclass
class Signals:
    """Individual similarity components for one candidate pair."""

    exact: float = 0.0
    jaro_winkler: float = 0.0
    levenshtein: float = 0.0
    token_jaccard: float = 0.0
    monge_elkan: float = 0.0
    synonym: float = 0.0
    value_profile: float = 0.0
    memory_prior: float = 0.0


@dataclass
class Candidate:
    """A scored source->target match with its supporting evidence."""

    source: str
    target: str
    score: float
    signals: Signals
    reasons: List[str] = field(default_factory=list)


# Blend weights (sum to 1.0, fixed denominator).  Value-profile and memory get
# the most pull because, when present, they are the strongest evidence; lexical
# signals form a robust fallback that always works even with zero sample data.
# A missing signal simply contributes 0 — we deliberately do NOT renormalize,
# so a lone strong signal is not diluted by the absent ones.
_WEIGHTS = {
    "value_profile": 0.22,
    "memory_prior": 0.20,
    "exact": 0.15,
    "synonym": 0.15,
    "monge_elkan": 0.10,
    "token_jaccard": 0.08,
    "jaro_winkler": 0.06,
    "levenshtein": 0.04,
}

# A single high-quality signal is, on its own, enough to trust a match.  These
# floors let such a signal cross the acceptance threshold even when every other
# signal is silent (e.g. two schemas that share nothing but the concept).
def _confidence_floor(sig: "Signals") -> float:
    floor = 0.0
    if sig.exact:
        floor = max(floor, 0.97)
    if sig.memory_prior >= 0.9:
        floor = max(floor, 0.95)
    if sig.synonym >= 1.0:
        floor = max(floor, 0.60)
    if sig.value_profile >= 0.75:  # distinctive type / real value overlap
        floor = max(floor, 0.60)
    # Two independent strong signals agreeing is high-confidence: a known
    # synonym whose values also match, or a value match with name overlap.
    if sig.synonym >= 1.0 and sig.value_profile >= 0.75:
        floor = max(floor, 0.90)
    if sig.value_profile >= 0.9 and (sig.token_jaccard >= 0.5 or sig.monge_elkan >= 0.85):
        floor = max(floor, 0.90)
    return floor


def score_pair(
    source: str,
    target: str,
    source_profile: Optional[ColumnProfile] = None,
    target_profile: Optional[ColumnProfile] = None,
    memory: Optional[MappingMemory] = None,
) -> Candidate:
    """Score a single source/target field pair across all signals."""
    ns, nt = normalize(source), normalize(target)
    ts, tt = tokenize(source), tokenize(target)
    sig = Signals()
    reasons: List[str] = []

    sig.exact = 1.0 if ns == nt and ns != "" else 0.0
    if sig.exact:
        reasons.append("identical normalized name")

    sig.jaro_winkler = similarity.jaro_winkler(ns.replace(" ", ""), nt.replace(" ", ""))
    sig.levenshtein = similarity.levenshtein_ratio(ns.replace(" ", ""), nt.replace(" ", ""))
    sig.token_jaccard = similarity.jaccard(ts, tt)
    sig.monge_elkan = similarity.symmetric_monge_elkan(ts, tt) if ts and tt else 0.0
    if sig.token_jaccard >= 0.5 or sig.monge_elkan >= 0.85:
        reasons.append("overlapping name tokens")

    sig.synonym = knowledge.synonym_score(ns, nt)
    if sig.synonym:
        reasons.append("known synonym / abbreviation")

    # The value signal is only meaningful when at least one side carries real
    # sampled values.  If both profiles are name-derived hints the "value"
    # comparison is just re-encoding the names, which the lexical/synonym
    # signals already cover — so we suppress it to avoid double counting.
    value_available = (
        source_profile is not None
        and target_profile is not None
        and not (source_profile.from_name and target_profile.from_name)
    )
    if value_available:
        sig.value_profile = profile_similarity(source_profile, target_profile)
        if sig.value_profile >= 0.5:
            reasons.append(
                f"value profiles agree (type={target_profile.semantic_type})"
            )

    if memory is not None:
        sig.memory_prior = memory.prior(source, target)
        if sig.memory_prior >= 0.5:
            reasons.append("confirmed in past mappings")

    # Fixed-weight blend: a missing signal contributes 0 and we do NOT
    # renormalize, so combining many weak signals stays conservative while the
    # confidence floors below let a single strong signal still win.
    score = sum(getattr(sig, k) * w for k, w in _WEIGHTS.items())
    score = max(score, _confidence_floor(sig))

    return Candidate(source=source, target=target, score=round(min(score, 1.0), 4),
                     signals=sig, reasons=reasons)


def rank_candidates(
    source: str,
    targets: List[str],
    source_profile: Optional[ColumnProfile] = None,
    target_profiles: Optional[Dict[str, ColumnProfile]] = None,
    memory: Optional[MappingMemory] = None,
    top_k: int = 3,
) -> List[Candidate]:
    """Return the ``top_k`` best target matches for one source field."""
    target_profiles = target_profiles or {}
    scored = [
        score_pair(
            source, t, source_profile, target_profiles.get(t), memory
        )
        for t in targets
    ]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]


def resolve_assignment(
    sources: List[str],
    targets: List[str],
    source_profiles: Optional[Dict[str, ColumnProfile]] = None,
    target_profiles: Optional[Dict[str, ColumnProfile]] = None,
    memory: Optional[MappingMemory] = None,
    threshold: float = 0.35,
) -> List[Candidate]:
    """Resolve a globally consistent one-to-one mapping.

    Scores the full source x target grid, then greedily assigns the highest
    scoring pairs first while enforcing that each source and each target is used
    at most once.  Greedy assignment on a well-calibrated score is both fast and
    close to optimal for the near-diagonal grids typical of schema matching.
    """
    source_profiles = source_profiles or {}
    target_profiles = target_profiles or {}

    grid: List[Candidate] = []
    for s in sources:
        for t in targets:
            grid.append(
                score_pair(
                    s, t,
                    source_profiles.get(s),
                    target_profiles.get(t),
                    memory,
                )
            )
    grid.sort(key=lambda c: c.score, reverse=True)

    used_sources = set()
    used_targets = set()
    assignment: List[Candidate] = []
    for cand in grid:
        if cand.score < threshold:
            break
        if cand.source in used_sources or cand.target in used_targets:
            continue
        used_sources.add(cand.source)
        used_targets.add(cand.target)
        assignment.append(cand)

    return assignment
