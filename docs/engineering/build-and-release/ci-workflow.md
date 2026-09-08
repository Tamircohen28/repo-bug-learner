# CI workflow

- **`.github/workflows/ci.yml`** — ruff lint; `make test` (semgrep precision corpora,
  scan regression tests, pytest) across a Python 3.11/3.12/3.13 matrix; agent-file
  drift checks; secret grep. Each matrix leg asserts that the venv it built runs the
  version the leg pins, because the Makefile otherwise selects an interpreter by
  probing `PATH`.
- **`.github/workflows/release.yml`** — manual version tag + GitHub Release

Precision corpora require every Opengrep rule to score ≥75% on positive/negative test snippets.
