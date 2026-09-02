"""Command line: inspect a template, preview a mapping, or build the upload."""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional

from .pipeline import load, read_source
from .template import read_template


def _cmd_inspect(args: argparse.Namespace) -> int:
    """Show what the tool worked out about a template, with no data involved."""
    schema, _wb, _sheet = read_template(args.template, sheet_name=args.sheet)
    print(f"\nTemplate : {args.template}")
    print(f"Sheet    : {schema.sheet_name}")
    print(f"Layout   : label row {_row(schema.label_row)}, "
          f"technical row {_row(schema.technical_row)}, "
          f"marker row {_row(schema.marker_row)}")
    print(f"Schema   : {schema.summary()}\n")

    width = max((len(f.name) for f in schema.fields), default=10)
    for f in schema.fields:
        flag = "*" if f.required else " "
        print(f"  {flag} {f.name:<{width}}  {f.describe()}")
        if args.verbose and f.label and f.label != f.name:
            print(f"    {'':<{width}}    label: {f.label}")
        if args.verbose and f.allowed:
            print(f"    {'':<{width}}    values: {', '.join(f.allowed[:8])}")
    for note in schema.notes:
        print(f"\n  note: {note}")
    print()
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    result = load(
        source_path=args.source,
        template_path=args.template,
        output_path=None if args.dry_run else args.output,
        memory_path=args.memory,
        sheet_name=args.sheet,
        only_clean=args.only_clean,
        max_rows=args.max_rows,
        threshold=args.threshold,
        learn_threshold=args.learn_threshold,
        overrides=_parse_overrides(args.map),
    )

    print(f"\nSchema   : {result.schema.summary()}")
    print(f"Mapping  : {result.plan.summary()}\n")
    for m in result.plan.mappings:
        if m.source is None:
            mark, detail = "  --", "(no source column matched)"
        else:
            mark = f"{m.confidence:>4.0%}"
            detail = f"<- {m.source}"
            if m.transform.name != "identity":
                detail += f"  [{m.transform.name}]"
        required = "*" if (result.schema.by_name(m.target) or _blank()).required else " "
        print(f"  [{mark}] {required} {m.target:<30} {detail}")

    print(f"\nValidate : {result.validation.summary()}")
    for line in result.validation.top():
        print(f"  {line}")

    if args.recon:
        with open(args.recon, "w", encoding="utf-8") as fh:
            fh.write(result.recon.as_text())
        print(f"\nRecon    : written to {args.recon}")
    else:
        print()
        print(result.recon.as_text())

    if result.output_paths:
        print(f"\nUpload   : {result.rows_written:,} rows")
        for path in result.output_paths:
            print(f"           {path}")
    elif args.dry_run:
        print("\nDry run — no file written.")

    return 0 if result.validation.ok else 1


class _blank:
    required = False


def _row(index: Optional[int]) -> str:
    return "none" if index is None else str(index + 1)


def _parse_overrides(pairs: Optional[List[str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit(f"--map expects TARGET=SOURCE, got {item!r}")
        target, source = item.split("=", 1)
        out[target.strip()] = source.strip()
    return out


def _cmd_connect(args: argparse.Namespace) -> int:
    """Talk to S/4. Read-only unless SAPLOAD_ALLOW_POST was set deliberately."""
    from .config import ConfigError, from_env, missing_settings
    from .sapclient import S4Client, SapError

    try:
        settings = from_env()
    except ConfigError as exc:
        print(f"\n  {exc}\n")
        missing = missing_settings()
        if missing:
            print("  Not set: " + ", ".join(sorted(missing)))
        print("\n  Set them in your shell, not in a file and not on this command "
              "line —\n  a command line ends up in history and in process listings.\n")
        return 2

    print(f"\n  {settings.describe()}\n")
    client = S4Client(settings)

    if args.action == "ping":
        ok, message = client.ping()
        print(f"  {'OK  ' if ok else 'FAIL'}  {message}\n")
        return 0 if ok else 1

    if args.action == "value-help":
        from .valuehelp import fetch_value_help
        schema, _wb, _sheet = read_template(args.template)
        try:
            sets = fetch_value_help(client, schema, cache_path=args.cache)
        except SapError as exc:
            print(f"  {exc}\n")
            return 1
        if not sets:
            print("  No template field matched a read API in the catalogue.\n")
        for vs in sets.values():
            print(f"  {vs.describe()}")
        print()
        return 0

    if args.action == "reconcile":
        from .readback import reconcile
        _fields, rows = read_source(args.sent)
        try:
            report = reconcile(client, rows, reference_field=args.reference,
                               amount_field=args.amount)
        except SapError as exc:
            print(f"  {exc}\n")
            return 1
        text = report.as_text()
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"  Written to {args.out}\n")
        else:
            print(text)
        return 0 if report.ok else 1

    return 2


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sapload",
        description="Fill an SAP upload template from a legacy extract.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="show the schema derived from a template")
    p_inspect.add_argument("template")
    p_inspect.add_argument("--sheet", help="sheet name, if not auto-detected")
    p_inspect.add_argument("-v", "--verbose", action="store_true")
    p_inspect.set_defaults(func=_cmd_inspect)

    p_build = sub.add_parser("build", help="map, validate and write the upload file")
    p_build.add_argument("source", help="legacy extract (.csv or .xlsx)")
    p_build.add_argument("template", help="SAP upload template (.xlsx)")
    p_build.add_argument("output", nargs="?", default="upload.xlsx")
    p_build.add_argument("--sheet")
    p_build.add_argument("--memory", help="mapping memory file, so next run is instant")
    p_build.add_argument("--recon", help="write the reconciliation pack here")
    p_build.add_argument("--map", action="append", metavar="TARGET=SOURCE",
                         help="pin a mapping the matcher got wrong (repeatable)")
    p_build.add_argument("--only-clean", action="store_true",
                         help="hold back rows that failed validation")
    p_build.add_argument("--max-rows", type=int, metavar="N",
                         help="split the output every N rows, to stay inside the "
                              "upload app's per-file limit (F2548 caps at 999)")
    p_build.add_argument("--threshold", type=float, default=0.35)
    p_build.add_argument("--learn-threshold", type=float, default=0.85,
                         help="only remember matches at or above this confidence "
                              "(reviewer overrides are always remembered)")
    p_build.add_argument("--dry-run", action="store_true")
    p_build.set_defaults(func=_cmd_build)

    p_conn = sub.add_parser("connect", help="talk to S/4HANA Cloud (read-only by default)")
    p_conn.add_argument("action", choices=["ping", "value-help", "reconcile"])
    p_conn.add_argument("--template", help="template to fetch value help for")
    p_conn.add_argument("--cache", help="where to cache fetched value help")
    p_conn.add_argument("--sent", help="the extract that was loaded")
    p_conn.add_argument("--reference", default="reference",
                        help="column in that extract holding the SAP reference")
    p_conn.add_argument("--amount", help="column holding the amount, to agree values")
    p_conn.add_argument("--out", help="write the reconciliation here")
    p_conn.set_defaults(func=_cmd_connect)

    args = parser.parse_args(argv)
    if args.command == "connect":
        if args.action == "value-help" and not args.template:
            parser.error("connect value-help needs --template")
        if args.action == "reconcile" and not args.sent:
            parser.error("connect reconcile needs --sent")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
