"""End-to-end demo: map a messy source schema onto a clean target schema.

Run from the repo root:  python examples/demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartmapper import SmartFieldMapper, MappingMemory, read_csv  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    src_fields, src_rows = read_csv(os.path.join(HERE, "source_customers.csv"))
    tgt_fields, tgt_rows = read_csv(os.path.join(HERE, "target_schema.csv"))

    mapper = SmartFieldMapper(memory=MappingMemory())

    print("SOURCE fields:", src_fields)
    print("TARGET fields:", tgt_fields)
    print("\nThe mapper never saw these before. It figures out the wiring:\n")

    plan = mapper.map_schema(
        src_fields, tgt_fields,
        source_rows=src_rows, target_rows=tgt_rows,
    )
    print(plan.summary(), "\n")
    for m in plan.mappings:
        arrow = f"{m.target:<16} <- {str(m.source):<12}"
        xf = "" if m.transform.name == "identity" else f"  ⟳ {m.transform.name}"
        why = f"   ({', '.join(m.reasons)})" if m.reasons else ""
        print(f"  [{m.confidence:>4.0%}] {arrow}{xf}{why}")

    print("\nNow CONNECT it — transform the source data into the target schema:\n")
    out = mapper.connect(plan, src_rows)
    for row in out:
        print("  ", row)


if __name__ == "__main__":
    main()
