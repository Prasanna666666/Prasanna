# Contributing

1. `make install`, then `make check` must pass (ruff, mypy, pytest).
2. Keep layers apart: `search/`, `indexing/`, `agent/`, `people/` never import `ui/`; only `bootstrap.py` constructs concrete ML classes.
3. New ML backends implement the Protocols in `ml/protocols.py`; test with fakes (`tests/conftest.py`).
4. Never write outside `Paths.root` or the export folder; go through `WriteGuard`.
5. UI: every interactive control needs a descriptive label/help text; no hard-coded colour-only signals.
