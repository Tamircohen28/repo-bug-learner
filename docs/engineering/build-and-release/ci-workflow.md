# CI workflow

- **`.github/workflows/ci.yml`** — ruff lint, scan regression tests, secret grep
- **`.github/workflows/regression-tests.yml`** — legacy alias for scan + semgrep precision (merged into ci.yml over time)
- **`.github/workflows/release.yml`** — manual version tag + GitHub Release

Precision corpora require every Opengrep rule to score ≥75% on positive/negative test snippets.
