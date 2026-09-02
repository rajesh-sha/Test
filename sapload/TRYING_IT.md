# sapload — try it in two minutes

No installation. No dependencies. Python 3.9+ and nothing else.

## 1. See what it makes of a template

    python -m sapload.cli inspect "examples/Supplier Invoice_EN.xlsx" -v

Nothing is configured. It works out for itself where the header block ends,
which row carries the technical field names, which fields are mandatory or
key, how long each may be, and what values each will accept.

## 2. Run the whole thing

    python -m sapload.cli build \
        examples/fsm_subcontractor_claims.csv \
        "examples/Supplier Invoice_EN.xlsx" \
        upload.xlsx \
        --map DocumentHeaderText=descr \
        --memory mappings.json \
        --recon recon.txt

Open `upload.xlsx` in Excel. SAP's header rows, dropdowns, column widths and
Field List sheet are exactly as they were — click a Currency cell and the
dropdown is still there.

Then run it again *without* `--map`. It remembers.

## 3. The guided walkthrough

    python examples/demo_sapload.py

## 4. The tests

    python -m unittest tests.test_sapload -v      # 36 tests
    python -m unittest tests.test_smartmapper     # 23 tests

---

# Trying it on a REAL SAP template

This is the part worth your time. Download a real template from your tenant —
Migration Cockpit, or the Fiori upload app — and run:

    python -m sapload.cli inspect "your_template.xlsx" -v

Read what it says at the bottom. If it reports a technical-name row and a
marker row, the schema is complete and the tool is working properly. If it
says it could not find them, the schema is thinner and it tells you so
rather than pretending.

Then point it at a real extract:

    python -m sapload.cli build extract.csv "your_template.xlsx" out.xlsx --dry-run

`--dry-run` maps and validates but writes nothing. Safe on any file.

## What to look for

- **Coverage.** Below ~85% on first sight of a template usually means the
  source column names need a vocabulary entry, not that the tool is broken.
- **The review tier.** Anything at 50-85% is the tool saying "probably, but
  look". That is the tail you should actually read.
- **Validation errors.** These are the ones SAP would have rejected. If it
  finds nothing on real data, be suspicious rather than pleased.

## Fixing a mapping it got wrong

    --map TargetField=source_column

Repeatable. With `--memory`, you only do it once per template.

## Teaching it your vocabulary

Edit `sapload/vocabulary.py` and add to `SAP_SYNONYM_GROUPS`:

    ["your term", "what SAP calls it", "what the legacy system calls it"],

This is the cheapest accuracy improvement available. No model, no training,
no network call.

## Staying inside the upload app's limits

    --max-rows 999

Writes `out_01.xlsx`, `out_02.xlsx`, ... The general journal app caps at 999
entries per file; check the limit for your app.

---

# Two things to verify before this goes near production

1. **Mid-file failure behaviour.** Upload a 10-row file with a deliberately
   bad row 6 and see what happens to rows 1-5. Whether earlier rows stay
   posted is not documented, and it determines whether you need idempotent
   re-submission. This is the one operational unknown.

2. **Template format.** SAP sometimes delivers Migration Cockpit templates as
   Excel 2003 XML with an `.xlsx` extension. That is plain XML, not a zip.
   The tool detects it and tells you to re-download as XLSX or CSV.

---

# Scope

Built for recurring, post-go-live loads through SAP's own spreadsheet upload
apps. Not a cutover tool — initial migration belongs in the Migration
Cockpit. It never connects to SAP: a person uploads a file they have already
seen validated, which keeps the human control point auditors expect.
