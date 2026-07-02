"""Command-line interface for smartmapper.

Two subcommands:

    smartmapper map     source.csv target.csv        # suggest a mapping
    smartmapper connect source.csv target.csv out.csv  # map + apply -> out.csv

``target.csv`` supplies the *target schema* (its header, and optionally sample
rows for value profiling).  ``source.csv`` is the data being remapped.
"""

from __future__ import annotations

import argparse
import sys
from typing import List

from .engine import SmartFieldMapper, read_csv, write_csv
from .memory import MappingMemory

_STATUS_ICON = {"auto": "✓", "review": "~", "low": "?", "unmatched": "✗"}


def _load_mapper(memory_path: str | None) -> SmartFieldMapper:
    memory = MappingMemory(memory_path) if memory_path else None
    return SmartFieldMapper(memory=memory)


def _print_plan(plan) -> None:
    print("\n" + plan.summary() + "\n")
    width = max((len(m.target) for m in plan.mappings), default=6)
    for m in plan.mappings:
        icon = _STATUS_ICON[m.status]
        src = m.source if m.source else "—"
        conf = f"{m.confidence:.0%}" if m.source else "  —"
        line = f"  {icon} {m.target:<{width}} <- {src:<{width}}  [{conf:>4}]"
        if m.transform.name != "identity":
            line += f"  ⟳ {m.transform.name}"
        print(line)
        if m.reasons and m.status in ("review", "low"):
            print(f"      · {', '.join(m.reasons)}")
    if plan.unmatched_sources:
        print(f"\n  unmatched source fields: {', '.join(plan.unmatched_sources)}")
    print()


def cmd_map(args) -> int:
    src_fields, src_rows = read_csv(args.source)
    tgt_fields, tgt_rows = read_csv(args.target)
    mapper = _load_mapper(args.memory)
    plan = mapper.map_schema(
        src_fields, tgt_fields,
        source_rows=src_rows, target_rows=tgt_rows,
        threshold=args.threshold,
    )
    _print_plan(plan)
    if args.memory and args.learn:
        mapper.learn(plan)
        mapper.memory.save()
        print(f"  learned {len(mapper.memory)} pairs -> {args.memory}\n")
    return 0


def cmd_connect(args) -> int:
    src_fields, src_rows = read_csv(args.source)
    tgt_fields, tgt_rows = read_csv(args.target)
    mapper = _load_mapper(args.memory)
    plan = mapper.map_schema(
        src_fields, tgt_fields,
        source_rows=src_rows, target_rows=tgt_rows,
        threshold=args.threshold,
    )
    _print_plan(plan)
    out_rows = mapper.connect(plan, src_rows)
    write_csv(args.output, tgt_fields, out_rows)
    print(f"  wrote {len(out_rows)} rows -> {args.output}\n")
    if args.memory and args.learn:
        mapper.learn(plan)
        mapper.memory.save()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="smartmapper",
        description="Super-smart field/schema mapper.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("source", help="Source CSV (data to remap)")
    common.add_argument("target", help="Target CSV (defines target schema)")
    common.add_argument("--memory", help="Path to a mappings memory JSON file")
    common.add_argument("--learn", action="store_true",
                        help="Save confirmed mappings back to memory")
    common.add_argument("--threshold", type=float, default=0.35,
                        help="Minimum confidence to accept a match (default 0.35)")

    m = sub.add_parser("map", parents=[common], help="Suggest a mapping")
    m.set_defaults(func=cmd_map)

    c = sub.add_parser("connect", parents=[common],
                       help="Suggest a mapping and apply it to produce output")
    c.add_argument("output", help="Output CSV in the target schema")
    c.set_defaults(func=cmd_connect)
    return p


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
