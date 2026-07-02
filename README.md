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
