# 🧠 smartmapper — a super-smart field & schema mapper

Mapping one dataset's fields onto another's is one of the most tedious, most
repeated chores in data work: `CustEmail → email`, `fname → first_name`,
`DOB → date_of_birth`, hundreds of times, by hand, every time a new file
lands. **smartmapper does the wiring for you** — it proposes the whole mapping
with confidence scores, human-readable reasons, and the transform each field
needs, then applies it to your data in one step. What took an afternoon takes
a few seconds of review.

Zero dependencies. Pure standard-library Python. Runs anywhere.

```
8 target fields | 4 auto, 3 review, 0 low-confidence, 1 unmatched | coverage 88%

  [ 90%] email            <- CustEmail     ⟳ lowercase
  [ 60%] first_name       <- fname         ⟳ split_first_name
  [ 90%] date_of_birth    <- DOB           ⟳ to_iso_date
  [ 90%] phone            <- Cell
  [ 90%] postal_code      <- ZipCode
  [  0%] lifetime_value   <- —             (needs a human — flagged, not guessed)
```

## Why this is more than fuzzy string matching

The productivity win comes from **stacking every available signal** into one
calibrated confidence score, because no single trick is reliable on its own.
This mirrors the state of the art in the schema-matching literature, where the
best systems combine lexical, semantic, and instance-based (value) evidence
rather than relying on names alone.

| Signal | What it catches | Example |
|---|---|---|
| **Exact / normalized name** | camelCase, snake_case, punctuation noise | `customerEmailAddress` ≡ `customer_email_addr` |
| **Jaro-Winkler + Levenshtein** | typos & abbreviations (prefix-weighted) | `qty` → `quantity` |
| **Token Jaccard + Monge-Elkan** | reordered / multi-word names | `home phone number` → `phone (home)` |
| **Synonym / abbreviation KB** | semantic gaps names can't bridge | `dob` → `date_of_birth`, `zip` → `postal_code` |
| **Value-based profiling** | the truth in the data, not the label | a column *of emails* → the field named `email`, even if the column is called `col_7` |
| **Active-learning memory** | never solve the same mapping twice | a confirmed pair maps at 95% next time |

When a field has **no sample data**, smartmapper still infers an *expected*
type from its name (a field named `phone` expects phone-shaped values), so the
value signal keeps working even on schema-only inputs.

Every match ships with the **reasons** it fired and a suggested
**transform** (ISO-date normalization, full-name splitting, currency
stripping, boolean coercion, …), and the assignment is resolved **one-to-one**
so no target ever double-books a source.

## Install

Nothing to install — it's pure standard library. Clone and go:

```bash
git clone <repo> && cd Test
python -m smartmapper.cli --help
```

(Or `pip install -e .` to get the `smartmapper` command on your PATH.)

## Command line

```bash
# Suggest a mapping (target.csv defines the target schema)
python -m smartmapper.cli map   source.csv target.csv

# Suggest AND apply — writes data in the target schema
python -m smartmapper.cli connect source.csv target.csv out.csv

# Learn from confirmed mappings so next time is instant
python -m smartmapper.cli map source.csv target.csv --memory mem.json --learn
```

Try it on the bundled example:

```bash
python examples/demo.py
```

## Library

```python
from smartmapper import SmartFieldMapper, MappingMemory

mapper = SmartFieldMapper(memory=MappingMemory("mappings.json"))

plan = mapper.map_schema(
    source_fields=["CustEmail", "fname", "DOB"],
    target_fields=["email", "first_name", "date_of_birth"],
    source_rows=source_sample,   # optional — a big accuracy boost
)

print(plan.summary())
for m in plan.mappings:
    print(m.target, "<-", m.source, f"{m.confidence:.0%}", m.transform.name)

target_rows = mapper.connect(plan, source_rows)   # apply the mapping
mapper.learn(plan)                                 # remember it
mapper.memory.save()
```

### Confidence tiers

| Tier | Confidence | Meaning |
|---|---|---|
| `auto` | ≥ 85% | Safe to apply without review |
| `review` | 50–85% | Very likely right — a glance confirms it |
| `low` | < 50% | A guess; needs a human |
| `unmatched` | — | No candidate cleared the bar — flagged, never guessed |

## Architecture

```
smartmapper/
  text.py        normalization + tokenization (camelCase, snake_case, …)
  similarity.py  Levenshtein, Jaro-Winkler, Jaccard, Monge-Elkan
  knowledge.py   editable synonym / abbreviation knowledge base
  profiling.py   value-based column profiling + name-based type hints
  transforms.py  transform detection & application (dates, names, currency…)
  memory.py      active-learning store of confirmed mappings (JSON)
  matcher.py     the ensemble: scores every pair, resolves 1:1 assignment
  engine.py      high-level SmartFieldMapper + connect() + CSV IO
  cli.py         `smartmapper map` / `smartmapper connect`
tests/           23 unit tests, run with `python -m unittest`
examples/        runnable demo + sample CSVs
```

## Extending it

- **Add your house vocabulary:** append term groups to
  `SYNONYM_GROUPS` in `knowledge.py`.
- **Add a transform:** register a `Transform` in `transforms.py` and teach
  `suggest_transform` when to pick it.
- **Tune aggressiveness:** adjust `--threshold` (CLI) or the signal
  `_WEIGHTS` / confidence floors in `matcher.py`.

## Tests

```bash
python -m unittest tests.test_smartmapper -v
```

---

# 📄 sapload — fill an SAP upload template, provably

`smartmapper` solves half the problem: given two schemas, wire them together.
`sapload` supplies the other half for SAP work — **it works out the target
schema for itself by reading the SAP template**, then validates, fills and
reconciles.

Nothing is configured per object. Hand it `Supplier Invoice_EN.xlsx`,
`JournalEntry_Template.xlsx`, or next release's replacement, and it works out
where the header block ends, which row carries the technical field names, which
fields are mandatory, how long each may be, and what values each will accept.

```bash
# What does this template actually want?
python -m sapload.cli inspect "Supplier Invoice_EN.xlsx"

# Map an extract onto it, validate every row, write the upload file
python -m sapload.cli build claims.csv "Supplier Invoice_EN.xlsx" upload.xlsx \
    --memory mappings.json --recon recon.txt
```

```
Schema   : 12 fields | 8 required | 3 with value help | data starts at row 6
Mapping  : 12 target fields | 3 auto, 9 review, 0 low-confidence, 0 unmatched | coverage 100%

  [ 60%] * SupplierInvoiceIDByInvcgParty  <- claim_number
  [ 90%] * DocumentDate                   <- invoice_dt  [to_iso_date]
  [ 97%]   CostCenter                     <- cost_centre
  [ 60%] * GLAccount                      <- gl_acct

Validate : 40 rows | 35 clean, 5 with errors
  [   2x] DocumentCurrency: not one of the template's allowed values (AUD, NZD, USD)  (rows 5, 29)
  [   1x] GLAccount: required by the template but empty  (rows 10)
  [   1x] InvoiceGrossAmount: expected a number  (rows 15)
  [   1x] DocumentHeaderText: longer than the template allows (57 > 25)  (rows 22)
```

Try it: `python examples/demo_sapload.py`

## Why read the template rather than the API metadata

SAP's OData `$metadata` is rich on structure and silent on the two things that
actually stop a document posting. Parsing two real S/4 services
(`API_SALES_ORDER_SRV`, `API_PURCHASEREQ_PROCESS_SRV`) gives **584 field
labels, 209 create-eligibility flags — and zero value-list annotations and zero
non-key mandatory markers.** Every `Nullable="false"` property in both services
is a key field.

The spreadsheet template carries what the metadata does not:

| Needed to fill a document | In `$metadata` | In the template |
|---|---|---|
| Field labels and types | Yes | Yes |
| **Which fields are mandatory** | **No** | Yes — the marker row |
| **Allowed values** | **No** | Yes — the dropdowns |
| Field lengths | Yes | Yes |

So the template is the better source of truth, and it needs no connection, no
communication arrangement and no credentials to read.

## What it does

| Step | Behaviour |
|---|---|
| **Derive** | Header-block detection, technical/label/marker/length rows, types from the data, value help from the dropdowns |
| **Map** | `smartmapper` plus an SAP finance vocabulary, matching against **both** the technical name and the human label and keeping the better |
| **Validate** | Rules derived from the template, never hand-written — add a column and it is checked on the next run |
| **Fill** | Rewrites only the sheet's data; SAP's styling, dropdowns, column widths and help sheets survive byte-for-byte |
| **Reconcile** | Counts in/out, control totals per numeric field, coverage, unmapped fields, and a sign-off block |

## Two deliberate design decisions

**Matching against the label as well as the technical name.** A source column
called `gl_acct` is far closer to the label "G/L Account" than to `GLAccount`.
Running both passes and keeping the better one lifted coverage from 67% to 92%
on the worked example, and on a tie the label wins — long compound technical
names share generic tokens (`id`, `by`, `party`) with unrelated columns and
score spuriously.

**Memory only learns what a human would stand behind.** Reviewer overrides are
always remembered; everything else must clear `--learn-threshold` (0.85 by
default). Auto-learning an unreviewed 60% guess is how a tool like this quietly
entrenches a wrong mapping — the guess becomes a prior, the prior raises the
score, and by run three nobody questions it.

## Extending it

- **House vocabulary:** `sapload.vocabulary.extend([["your term", "our term"]])`
- **New object:** nothing to do. Point it at the template.
- **Client-specific templates:** `--sheet` if the data sheet is not auto-detected.

## Scope

Built for **recurring, post-go-live, business-user loads** through SAP's own
spreadsheet upload apps. It is not a cutover tool — initial migration belongs in
the SAP S/4HANA Migration Cockpit, which has full object coverage and SAP
support. It never connects to SAP: a person uploads a file they have already
seen validated, which keeps the human control point auditors expect.

## Tests

```bash
python -m unittest tests.test_sapload -v    # 27 tests
python -m unittest tests.test_smartmapper   # 23 tests
```

---

## Design notes & references

The ensemble design follows the consensus in automated schema-matching
research that combining name-based, semantic, and instance/value-based
matchers with an active-learning feedback loop outperforms any single matcher:

- [A survey of approaches to automatic schema matching — *The VLDB Journal*](https://dl.acm.org/doi/10.1007/s007780100057)
- [Semantic-Similarity-Based Schema Matching (*Energies*, 2022)](https://www.mdpi.com/1996-1073/15/23/8894)
- [SMAT: an attention-based deep learning solution to schema matching](https://pmc.ncbi.nlm.nih.gov/articles/PMC8487677/)
- [Automatic End-to-End Data Integration using Large Language Models](https://arxiv.org/pdf/2603.10547)
- [Knowledge Graph-based RAG for Schema Matching](https://arxiv.org/pdf/2501.08686)

smartmapper deliberately implements the classic, transparent, zero-dependency
core of these ideas (explainable signals, no model download, no network) so it
runs anywhere and every decision is auditable — a natural base to later swap in
learned embeddings for the synonym layer.
