# AGENTS.md

## Cursor Cloud specific instructions

`smartmapper` is a zero-dependency, pure-standard-library Python package (the
`smartmapper` CLI + importable library). It maps one dataset's fields onto
another's. The `web/` folder holds unrelated, self-contained static HTML
workbenches (offline field-mapping tools) that need no build step.

### Environment

- A virtualenv lives at `.venv/` (created by the startup update script). Activate
  it with `source .venv/bin/activate` before running any Python/CLI/test command.
- The package is installed editable (`pip install -e ".[dev]"`), so source edits
  take effect immediately with no reinstall. Only re-run the update script if you
  change `pyproject.toml` dependencies.

### Commands (from repo root, venv activated)

- Tests: `python -m unittest tests.test_smartmapper -v` (also `python -m pytest -q`). 23 tests.
- Run the library demo: `python examples/demo.py`.
- CLI (map): `smartmapper map examples/source_customers.csv examples/target_schema.csv`.
- CLI (map + apply): `smartmapper connect examples/source_customers.csv examples/target_schema.csv out.csv`.
- No linter/formatter is configured; there is no lint step beyond `python -m py_compile`.

### Web workbenches

- Static HTML only. Serve locally with `python3 -m http.server 8765` run from
  the `web/` directory, then open e.g.
  `http://localhost:8765/mdfs-field-mapping-workbench.html`. No backend/API.
