"""Run me if the workbench will not start:  python check.py

Prints what is wrong in plain terms rather than a stack trace.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OK, BAD = "  OK   ", "  FAIL "


def main() -> int:
    print("\n  SAP Load Workbench — self check\n" + "  " + "-" * 52)
    problems = []

    version = sys.version_info
    if version >= (3, 9):
        print(f"{OK} Python {version.major}.{version.minor}.{version.micro}")
    else:
        print(f"{BAD} Python {version.major}.{version.minor} — 3.9 or later is needed")
        problems.append("Install Python 3.9+ from https://www.python.org/downloads/")

    print(f"       Running from {HERE}")
    for folder in ("sapload", "smartmapper"):
        if os.path.isdir(os.path.join(HERE, folder)):
            print(f"{OK} found the {folder} folder")
        else:
            print(f"{BAD} no {folder} folder here")
            problems.append(
                f"Run this from the folder that CONTAINS '{folder}'. If you "
                f"opened the zip without extracting it, extract it properly first."
            )

    if os.path.isfile(os.path.join(HERE, "sapload", "knowledge.json")):
        print(f"{OK} found the shared vocabulary file")
    else:
        print(f"{BAD} sapload/knowledge.json is missing")
        problems.append("The extraction is incomplete — unzip it again.")

    sys.path.insert(0, HERE)
    try:
        from sapload import read_template          # noqa: F401
        from sapload.vocabulary import synonym_groups
        print(f"{OK} the code imports cleanly "
              f"({len(synonym_groups())} vocabulary groups loaded)")
    except Exception as exc:                       # pragma: no cover
        print(f"{BAD} import failed: {exc}")
        problems.append("Something is missing from the folder — unzip it again.")

    workbench = os.path.join(HERE, "SAP-Load-Workbench.html")
    if os.path.isfile(workbench):
        print(f"{OK} found SAP-Load-Workbench.html — double-click it to start")
    else:
        print(f"{BAD} SAP-Load-Workbench.html is missing")
        problems.append("Unzip the pack again, or run: python build.py")

    sample = os.path.join(HERE, "examples", "Supplier Invoice_EN.xlsx")
    if os.path.isfile(sample):
        try:
            from sapload import read_template
            schema, _wb, _sheet = read_template(sample)
            print(f"{OK} read the sample template — {schema.summary()}")
        except Exception as exc:
            print(f"{BAD} could not read the sample template: {exc}")
            problems.append("The extraction may be damaged — unzip it again.")
    else:
        print("       (no sample template here — that is fine)")

    print("  " + "-" * 52)
    if problems:
        print("\n  What to do:\n")
        for i, item in enumerate(problems, start=1):
            print(f"    {i}. {item}\n")
        return 1

    print("\n  Everything checks out.\n")
    print("      Double-click  SAP-Load-Workbench.html    to use it")
    print("      python -m sapload.cli --help             to script it\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
