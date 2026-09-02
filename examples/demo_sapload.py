"""Walk through a load end to end, the way an operator would run it.

    python examples/demo_sapload.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from examples.make_sap_template import write_extract, write_template
from sapload import load, read_template

BAR = "=" * 74


def main() -> None:
    work = tempfile.mkdtemp(prefix="sapload-demo-")
    template = os.path.join(work, "Supplier Invoice_EN.xlsx")
    source = os.path.join(work, "fsm_subcontractor_claims.csv")
    upload = os.path.join(work, "upload.xlsx")
    memory = os.path.join(work, "mappings.json")
    write_template(template)
    write_extract(source, rows=40)

    print(f"\n{BAR}\n  1. READ THE TEMPLATE — nothing configured, everything derived\n{BAR}")
    schema, _wb, _sheet = read_template(template)
    print(f"  {schema.summary()}")
    print(f"  header block: label row {schema.label_row + 1}, "
          f"marker row {schema.marker_row + 1}, "
          f"technical row {schema.technical_row + 1}\n")
    for f in schema.fields[:5]:
        print(f"    {'*' if f.required else ' '} {f.name:<30} {f.describe()}")
    print(f"    … {len(schema.fields) - 5} more")

    print(f"\n{BAR}\n  2. MAP THE EXTRACT — first run, one field needs a human\n{BAR}")
    first = load(source, template, memory_path=memory)
    print(f"  {first.plan.summary()}")
    for m in first.plan.mappings:
        if m.source is None:
            print(f"    [ -- ] {m.target:<30} needs a decision")

    print(f"\n{BAR}\n  3. REVIEWER PINS IT — and it is remembered\n{BAR}")
    second = load(source, template, output_path=upload, memory_path=memory,
                  overrides={"DocumentHeaderText": "descr"})
    print(f"  {second.plan.summary()}")

    third = load(source, template, memory_path=memory)
    print(f"  next run, no override needed: {third.plan.summary()}")

    print(f"\n{BAR}\n  4. VALIDATE — before anything reaches SAP\n{BAR}")
    print(f"  {second.validation.summary()}\n")
    for line in second.validation.top():
        print(f"    {line}")

    print(f"\n{BAR}\n  5. THE RECONCILIATION PACK\n{BAR}")
    print(second.recon.as_text())
    print(f"\n  Upload file: {upload}")
    print("  SAP's formatting, dropdowns and help sheet are untouched.\n")


if __name__ == "__main__":
    main()
