# Changelog

See [docs/CHANGELOG.md](docs/CHANGELOG.md) for full history.

## [Unreleased]

### Fixed

- CI `lint` job no longer installs ruff unpinned. Ruff 0.16 widened its default rule
  set, which turned every fresh CI run red on an unchanged repo and blocked Dependabot
  PRs. The rule set is now declared explicitly in `[tool.ruff.lint]`, the version is
  pinned in the `dev` extra, and CI runs the documented `make lint` target rather than
  a divergent inline command.

### Changed

- `make lint` runs the pinned ruff via `uvx`, so it needs no prior `make install`;
  added `make lint-fix`.
- Timezone-aware datetimes throughout (`datetime.now(UTC)` instead of naive `now()`
  and deprecated `utcnow()`); `fromisoformat` now parses trailing `Z` natively.
- Every `subprocess.run` call declares `check=` explicitly.
- `scripts/precision_check.py` writes to a real temp directory instead of a fixed
  `/tmp` path.
- Vendored contract check scripts refreshed from `tamirs-superpowers@3.6.1` (were
  1.6.1). The newer `check-platform-targets.sh` cross-checks the capability registry,
  so each entry in `platform-targets.json` now names the platform that owns it.

### Added

- `core/capabilities/platforms.json` + `schema.json` — the single source of truth for
  what each supported agent surface (Claude Code, Cursor, Codex) can actually do.
  Every supported surface answers all 19 capability keys, nothing is claimed `native`
  without a validation command, and unmeasured surfaces (Claude Desktop, Cursor CLI,
  Codex IDE) are recorded as `unverified` with no capability claims rather than
  invented ones.
- `make skill-bridge` / `make skill-bridge-check` — `.claude/skills` is now a
  generated mirror of the canonical `.agents/skills`, asserted by `make agent:check`.
  The two trees were hand-copied and could diverge with the whole gate still green.
- Multi-platform README badges, platform-targets docs, and agent polish gates
- Portable canonical skill payload at `.agents/skills/repo-bug-review/`
- Root CHANGELOG mirror and versioning policy doc

## [0.1.0] - 2026-06-01

- Initial repo-bug-learner release — Jira/GitHub mining, rule synthesis, validation pipeline
