# Contributing

1. Fork and clone the repository.
2. `uv sync --extra dev` and `make test`.
3. Create a feature branch.
4. Update `docs/CHANGELOG.md` under `[Unreleased]` for user-visible changes.
5. Open a PR using the template.

Code style: `ruff` on `src/` and `scripts/`. Scalafix rules must compile in `rule-validator/`.
