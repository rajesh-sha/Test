"""Assemble SAP-Load-Workbench.html from src/ and the shared knowledge file.

    python build.py

The single-file workbench is a build output, not something to edit. It is
generated from the page shell, three JavaScript sources, and sapload/knowledge.json
— the same file the Python toolkit reads, so the vocabulary cannot drift
between the two runtimes.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
SRC = ROOT / "src"
OUT = ROOT / "SAP-Load-Workbench.html"
KNOWLEDGE = ROOT / "sapload" / "knowledge.json"
PARTS = ["1-xlsx.js", "2-engine.js", "3-ui.js"]
MARKER = "/*__KNOWLEDGE__*/"


def build() -> pathlib.Path:
    knowledge = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    payload = json.dumps({"synonyms": knowledge.get("synonyms", []),
                          "thresholds": knowledge.get("thresholds", {})},
                         separators=(",", ":"))

    scripts = []
    for name in PARTS:
        body = (SRC / name).read_text(encoding="utf-8")
        if MARKER in body:
            body = body.replace(MARKER + "{ synonyms: [], thresholds: {} }", payload)
        scripts.append(body)

    if MARKER not in "".join((SRC / n).read_text() for n in PARTS):
        raise SystemExit("No knowledge injection point found — check src/2-engine.js")

    doc = ((SRC / "shell.html").read_text(encoding="utf-8")
           + '<script>\n"use strict";\n'
           + "\n".join(scripts)
           + "\n</script>\n</body>\n</html>\n")
    OUT.write_text(doc, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    out = build()
    size = out.stat().st_size
    print(f"  built {out.name}  ({size:,} bytes)")
    body = out.read_text(encoding="utf-8")
    if MARKER in body:
        sys.exit("  the knowledge file was not injected")
    groups = len(json.loads(KNOWLEDGE.read_text(encoding="utf-8"))["synonyms"])
    print(f"  {groups} vocabulary groups inlined from sapload/knowledge.json")
