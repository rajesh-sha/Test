"""Guard the one thing that can silently diverge: the shared knowledge file.

The toolkit has two runtimes — Python for scheduling and the S/4 connection,
JavaScript for the file an operator double-clicks. Two implementations of the
same rules is how a tool starts giving two different answers, so the rules that
actually change live in one JSON file that both read.

These tests fail if that stops being true.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import build as builder                                   # noqa: E402
from sapload import valuehelp, vocabulary                 # noqa: E402

KNOWLEDGE = json.load(open(os.path.join(ROOT, "sapload", "knowledge.json"),
                           encoding="utf-8"))


class TestOneSourceOfTruth(unittest.TestCase):
    def test_python_reads_the_shared_vocabulary(self):
        self.assertEqual(vocabulary.synonym_groups(), KNOWLEDGE["synonyms"])

    def test_python_reads_the_shared_catalogue(self):
        self.assertEqual(len(valuehelp.CATALOGUE), len(KNOWLEDGE["value_help"]))

    def test_the_browser_build_carries_the_same_vocabulary(self):
        out = builder.build()
        body = out.read_text(encoding="utf-8")
        self.assertNotIn(builder.MARKER, body, "knowledge was not injected")
        # Every term the Python side knows must be present in the built file.
        for group in KNOWLEDGE["synonyms"]:
            for term in group:
                self.assertIn(f'"{term}"', body, f"missing from the build: {term}")

    def test_the_browser_build_carries_the_same_thresholds(self):
        body = builder.build().read_text(encoding="utf-8")
        for name, value in KNOWLEDGE["thresholds"].items():
            self.assertIn(f'"{name}":{value}', body.replace(", ", ","),
                          f"threshold not injected: {name}")

    def test_adding_a_term_reaches_both_runtimes(self):
        """The property that matters: one edit, both sides, no hand-syncing."""
        path = os.path.join(ROOT, "sapload", "knowledge.json")
        original = open(path, encoding="utf-8").read()
        try:
            edited = json.loads(original)
            edited["synonyms"].append(["zz house term", "zz client word"])
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(edited, fh, indent=2)

            vocabulary.reload()
            self.assertIn(["zz house term", "zz client word"],
                          vocabulary.synonym_groups())

            body = builder.build().read_text(encoding="utf-8")
            self.assertIn('"zz house term"', body)
        finally:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(original)
            vocabulary.reload()
            builder.build()

    def test_the_build_is_reproducible(self):
        first = builder.build().read_bytes()
        second = builder.build().read_bytes()
        self.assertEqual(first, second)

    def test_the_build_runs_as_a_command(self):
        result = subprocess.run([sys.executable, "build.py"], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("vocabulary groups inlined", result.stdout)


class TestNoStaleArtefacts(unittest.TestCase):
    def test_the_retired_local_server_is_gone(self):
        for name in ("serve.py", "ui.html"):
            self.assertFalse(os.path.exists(os.path.join(ROOT, "sapload", name)),
                             f"sapload/{name} should have been removed with the "
                             f"local-server mode")

    def test_the_built_file_is_not_edited_by_hand(self):
        """If someone edits the output, the next build silently discards it."""
        out = os.path.join(ROOT, "SAP-Load-Workbench.html")
        self.assertTrue(os.path.exists(out))
        before = open(out, "rb").read()
        builder.build()
        self.assertEqual(open(out, "rb").read(), before,
                         "SAP-Load-Workbench.html differs from a fresh build — "
                         "it was edited directly instead of via src/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
