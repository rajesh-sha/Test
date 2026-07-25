"""smartmapper — a super-smart, zero-dependency field/schema mapper.

Map fields from one dataset or schema onto another automatically.  Instead of a
human hand-wiring ``source_col -> target_col`` for hundreds of fields, the
ensemble matcher proposes the whole mapping with confidence scores, reasons and
transforms — turning an afternoon of tedium into a few seconds of review.

Quick start::

    from smartmapper import SmartFieldMapper, MappingMemory

    mapper = SmartFieldMapper(memory=MappingMemory("mappings.json"))
    plan = mapper.map_schema(
        source_fields=["CustEmail", "fname", "DOB"],
        target_fields=["email", "first_name", "date_of_birth"],
        source_rows=source_sample,   # optional, big accuracy boost
    )
    print(plan.summary())
    target_rows = mapper.connect(plan, source_rows)   # apply it
    mapper.learn(plan)                                 # remember for next time
"""

from .engine import (
    FieldMapping,
    MappingPlan,
    SmartFieldMapper,
    read_csv,
    write_csv,
)
from .knowledge import rebuild_index
from .matcher import (
    Candidate,
    rank_candidates,
    rank_sources_for_target,
    resolve_assignment,
    score_pair,
)
from .memory import MappingMemory
from .profiling import ColumnProfile, profile_column

__all__ = [
    "SmartFieldMapper",
    "MappingPlan",
    "FieldMapping",
    "MappingMemory",
    "ColumnProfile",
    "profile_column",
    "Candidate",
    "score_pair",
    "rank_candidates",
    "rank_sources_for_target",
    "resolve_assignment",
    "rebuild_index",
    "read_csv",
    "write_csv",
]

__version__ = "0.1.0"
