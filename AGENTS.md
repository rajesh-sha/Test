# AGENTS.md

## Cursor Cloud specific instructions

`smartmapper` is a zero-dependency, pure-standard-library Python package (a field/schema
mapper) plus a CLI. The `web/` directory holds standalone static HTML tools (workshop
capture / mapping workbench) that are opened directly in a browser — they have no build
step and are unrelated to the Python package.

Dev environment: a virtualenv at `.venv/` (gitignored) is created by the startup update
script, which installs the package editable with dev extras (`pip install -e ".[dev]"`,
which pulls in `pytest`). The `python3` interpreter is 3.12; there is no `python` alias, so
use `python3` or the venv binaries.

- Activate/use the venv binaries directly, e.g. `.venv/bin/python`, `.venv/bin/pytest`,
  `.venv/bin/smartmapper`.
- Tests: `.venv/bin/pytest tests/` (or `.venv/bin/python -m unittest tests.test_smartmapper`).
- Run the demo: `.venv/bin/python examples/demo.py`.
- CLI: `.venv/bin/smartmapper map|connect ...` (see `README.md`).
- No linter is configured in the repo (no ruff/flake8/black/pylint config). Byte-compiling
  with `.venv/bin/python -m py_compile smartmapper/*.py` is a lightweight syntax check.
- System note: `python3 -m venv` requires the `python3.12-venv` apt package (installed in
  the environment snapshot). If venv creation fails on a fresh pod, install it with
  `sudo apt-get install -y python3.12-venv`.
