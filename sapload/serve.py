"""A local web app for the people who actually run the weekly load.

The command line is fine for a developer and wrong for an AP clerk doing this
every Thursday.  This starts a small server on the operator's own machine and
opens a browser: drag in the SAP template and the extract, read the proposed
mapping, correct anything that looks wrong, download the filled template and
the reconciliation pack.

Nothing leaves the machine.  There is no database, no login and no SAP
connection — the files are held in memory for the length of one session and
discarded.  It is standard library only, so it runs from a folder on a
locked-down laptop, and the same module runs unchanged as a Cloud Foundry app
when it is time to share it.

    python -m sapload.serve            # opens http://127.0.0.1:8765
    python -m sapload.serve --port 80 --host 0.0.0.0 --no-browser
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import tempfile
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

from smartmapper import MappingMemory, SmartFieldMapper

from . import vocabulary
from .pipeline import map_with_aliases, read_source
from .recon import build_recon
from .template import read_template
from .validate import validate

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_UPLOAD = 48 * 1024 * 1024      # generous for a template plus an extract


# --------------------------------------------------------------------------- #
# Session state — one operator, one browser tab, held in memory
# --------------------------------------------------------------------------- #
class Session:
    """Whatever the current browser tab is working on."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tmpdir = tempfile.mkdtemp(prefix="sapload-ui-")
        self.memory = MappingMemory(os.path.join(self.tmpdir, "mappings.json"))
        self.reset()

    def reset(self) -> None:
        self.template_path: Optional[str] = None
        self.template_name = ""
        self.source_path: Optional[str] = None
        self.source_name = ""

    def stash(self, kind: str, filename: str, blob: bytes) -> str:
        safe = os.path.basename(filename).replace("..", "_") or f"{kind}.bin"
        path = os.path.join(self.tmpdir, f"{kind}__{safe}")
        with open(path, "wb") as fh:
            fh.write(blob)
        return path


SESSION = Session()


# --------------------------------------------------------------------------- #
# The work, expressed for a browser
# --------------------------------------------------------------------------- #
def analyse(overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Derive the schema, propose a mapping, and validate — without writing."""
    if not SESSION.template_path:
        raise UserError("Add the SAP template first.")
    if not SESSION.source_path:
        raise UserError("Add the extract you want to load.")

    vocabulary.install()
    schema, _wb, _sheet = read_template(SESSION.template_path)
    source_fields, source_rows = read_source(SESSION.source_path)
    if not source_rows:
        raise UserError(f"{SESSION.source_name} has no data rows.")

    mapper = SmartFieldMapper(memory=SESSION.memory)
    plan, _alias = map_with_aliases(mapper, schema, source_fields, source_rows)
    _apply(plan, overrides or {}, source_fields)

    rows = mapper.connect(plan, source_rows)
    report = validate(schema, rows)
    preview_fields = [f.name for f in schema.fields]

    return {
        "template": SESSION.template_name,
        "source": SESSION.source_name,
        "sourceFields": source_fields,
        "rowCount": len(source_rows),
        "schema": {
            "sheet": schema.sheet_name,
            "headerRows": schema.header_rows,
            "summary": schema.summary(),
            "notes": schema.notes,
            "labelRow": _human(schema.label_row),
            "technicalRow": _human(schema.technical_row),
            "markerRow": _human(schema.marker_row),
            "fields": [
                {
                    "name": f.name, "label": f.label, "required": f.required,
                    "key": f.key, "type": f.dtype, "maxLength": f.max_length,
                    "allowed": f.allowed, "describe": f.describe(),
                }
                for f in schema.fields
            ],
        },
        "mapping": {
            "summary": plan.summary(),
            "coverage": plan.coverage,
            "unusedSources": plan.unmatched_sources,
            "rows": [
                {
                    "target": m.target,
                    "source": m.source,
                    "confidence": round(m.confidence, 3),
                    "status": m.status,
                    "transform": m.transform.name,
                    "reasons": m.reasons,
                    "required": bool((schema.by_name(m.target) or _Blank()).required),
                }
                for m in plan.mappings
            ],
        },
        "validation": {
            "summary": report.summary(),
            "ok": report.ok,
            "rowCount": report.row_count,
            "cleanRows": report.clean_row_count,
            "badRows": len(report.bad_rows),
            "errorCount": len(report.errors),
            "warningCount": len(report.warnings),
            "top": report.top(),
            "issues": [
                {"row": i.row, "field": i.field, "severity": i.severity,
                 "message": i.message, "value": i.value}
                for i in report.issues[:400]
            ],
        },
        "preview": {
            "fields": preview_fields,
            "rows": [[_cell(r.get(f)) for f in preview_fields] for r in rows[:20]],
        },
    }


def build(
    overrides: Optional[Dict[str, str]] = None,
    only_clean: bool = False,
    max_rows: Optional[int] = None,
) -> Dict[str, Any]:
    """Write the filled template(s) and the reconciliation pack."""
    if not SESSION.template_path or not SESSION.source_path:
        raise UserError("Add both files first.")

    vocabulary.install()
    schema, wb, sheet = read_template(SESSION.template_path)
    source_fields, source_rows = read_source(SESSION.source_path)

    mapper = SmartFieldMapper(memory=SESSION.memory)
    plan, winning = map_with_aliases(mapper, schema, source_fields, source_rows)
    _apply(plan, overrides or {}, source_fields)

    mapped = mapper.connect(plan, source_rows)
    report = validate(schema, mapped)

    to_write = mapped
    notes = list(schema.notes)
    if only_clean and report.bad_rows:
        to_write = [r for i, r in enumerate(mapped, start=1) if i not in report.bad_rows]
        notes.append(f"{len(report.bad_rows)} row(s) with errors were held back "
                     f"at the operator's request.")

    stem = os.path.splitext(os.path.basename(SESSION.template_name))[0]
    cells = [schema.row_to_cells(r) for r in to_write]
    batches = _batch(cells, max_rows)
    files: List[Dict[str, str]] = []
    for index, chunk in enumerate(batches, start=1):
        suffix = "" if len(batches) == 1 else f"_{index:02d}"
        out_path = os.path.join(SESSION.tmpdir, f"{stem}_filled{suffix}.xlsx")
        wb.write_filled(out_path=out_path, sheet=sheet, data_rows=chunk,
                        keep_rows=schema.header_rows,
                        numeric_cols=schema.numeric_columns)
        with open(out_path, "rb") as fh:
            files.append({
                "name": os.path.basename(out_path),
                "rows": str(len(chunk)),
                "b64": base64.b64encode(fh.read()).decode("ascii"),
            })
    if len(batches) > 1:
        notes.append(f"Split into {len(batches)} files of at most {max_rows:,} rows.")

    recon = build_recon(
        source_name=SESSION.source_name, template_name=SESSION.template_name,
        schema=schema, source_rows=source_rows, mapped_rows=mapped,
        written_rows=to_write, plan_coverage=plan.coverage,
        unmapped_targets=[m.target for m in plan.mappings if m.source is None],
        unused_sources=plan.unmatched_sources, validation=report, notes=notes,
    )

    # Remember only what the operator confirmed, plus matches already strong
    # enough to have applied without review.
    confirmed = set(overrides or ())
    for m in plan.mappings:
        if m.source is None:
            continue
        if m.target not in confirmed and m.confidence < 0.85:
            continue
        SESSION.memory.confirm(m.source, m.target)
        alias = winning.get(m.target)
        if alias and alias != m.target:
            SESSION.memory.confirm(m.source, alias)
    SESSION.memory.save()

    return {
        "files": files,
        "rowsWritten": sum(len(c) for c in batches),
        "rowsHeldBack": len(mapped) - len(to_write),
        "recon": recon.as_text(),
        "reconName": f"{stem}_reconciliation.txt",
        "validationOk": report.ok,
    }


class UserError(Exception):
    """Something the operator can fix, shown as a message rather than a stack."""


class _Blank:
    required = False


def _human(index: Optional[int]) -> Optional[int]:
    return None if index is None else index + 1


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def _batch(rows: List, size: Optional[int]) -> List[List]:
    if not size or size <= 0 or len(rows) <= size:
        return [rows]
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def _apply(plan, overrides: Dict[str, str], source_fields) -> None:
    known = set(source_fields)
    for m in plan.mappings:
        if m.target not in overrides:
            continue
        chosen = overrides[m.target]
        if chosen and chosen not in known:
            raise UserError(f"{chosen!r} is not a column in the extract.")
        m.source = chosen or None
        m.confidence = 1.0 if chosen else 0.0
        m.reasons = ["chosen by the operator"]


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "sapload"

    def log_message(self, fmt, *args):        # quiet; this is a desktop tool
        pass

    # -- routing ---------------------------------------------------------- #
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send_file(os.path.join(HERE, "ui.html"), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json({
                "template": SESSION.template_name,
                "source": SESSION.source_name,
                "remembered": len(SESSION.memory),
            })
        else:
            self._json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
            with SESSION.lock:
                if self.path == "/api/upload":
                    self._json(self._upload(payload))
                elif self.path == "/api/analyse":
                    self._json(analyse(payload.get("overrides")))
                elif self.path == "/api/build":
                    self._json(build(
                        overrides=payload.get("overrides"),
                        only_clean=bool(payload.get("onlyClean")),
                        max_rows=_int_or_none(payload.get("maxRows")),
                    ))
                elif self.path == "/api/reset":
                    SESSION.reset()
                    self._json({"ok": True})
                else:
                    self._json({"error": "not found"}, status=404)
        except UserError as exc:
            self._json({"error": str(exc)}, status=400)
        except ValueError as exc:
            self._json({"error": str(exc)}, status=400)
        except Exception:                                  # pragma: no cover
            traceback.print_exc()
            self._json({"error": "Something went wrong reading those files. "
                                 "Check the terminal for detail."}, status=500)

    # -- actions ---------------------------------------------------------- #
    def _upload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        kind = payload.get("kind")
        if kind not in ("template", "source"):
            raise UserError("Unknown upload kind.")
        name = str(payload.get("name") or "")
        try:
            blob = base64.b64decode(payload.get("data") or "", validate=True)
        except (binascii.Error, ValueError):
            raise UserError(f"Could not read {name or 'that file'}.")
        if not blob:
            raise UserError(f"{name or 'That file'} is empty.")
        if len(blob) > MAX_UPLOAD:
            raise UserError(f"{name} is larger than "
                            f"{MAX_UPLOAD // (1024 * 1024)} MB.")

        path = SESSION.stash(kind, name, blob)
        if kind == "template":
            SESSION.template_path, SESSION.template_name = path, name
        else:
            SESSION.source_path, SESSION.source_name = path, name
        return {"ok": True, "kind": kind, "name": name, "bytes": len(blob)}

    # -- plumbing --------------------------------------------------------- #
    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_UPLOAD * 2:
            raise UserError("That file is too large.")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, body: Dict[str, Any], status: int = 200) -> None:
        blob = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(blob)

    def _send_file(self, path: str, content_type: str) -> None:
        try:
            with open(path, "rb") as fh:
                blob = fh.read()
        except OSError:
            self._json({"error": f"missing {os.path.basename(path)}"}, status=500)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)


def _int_or_none(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sapload.serve",
        description="Run the load workbench in a browser on this machine.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("PORT", 8765)))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print(f"\n  SAP load workbench running at {url}")
    print("  Files stay on this machine. Press Ctrl+C to stop.\n")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("  Stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
