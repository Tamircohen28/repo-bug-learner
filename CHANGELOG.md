# Changelog

See [docs/CHANGELOG.md](docs/CHANGELOG.md) for full history.

## [Unreleased]

### Fixed

- CI `lint` job no longer installs ruff unpinned. Ruff 0.16 widened its default rule
  set, which turned every fresh CI run red on an unchanged repo and blocked Dependabot
  PRs. The rule set is now declared explicitly in `[tool.ruff.lint]`, the version is
  pinned in the `dev` extra, and CI runs the documented `make lint` target rather than
  a divergent inline command.
- The test venv is built on a Python that meets the declared floor. `pyproject`
  requires `>=3.11`, but `make test`/`make precision` ran `python -m venv .venv`
  against ambient `python` — 3.10.4 on a pyenv machine, below the floor, silently.
  The Makefile now selects the first interpreter that clears 3.11 (override with
  `make test PYTHON=...`) and fails with a clear message when there is none, instead
  of the old `2>/dev/null || true` that surfaced as `no such file: .venv/bin/python`.
  Readiness is tracked by a stamp file rather than the `.venv` directory itself,
  because `make install` (`uv sync`) creates that directory without semgrep and on
  an interpreter of its own choosing — a directory target reads as up to date in
  both cases, so `make install && make test` reached the precision check with no
  `.venv/bin/semgrep`, and an existing 3.10 venv slipped past the floor entirely.
- `actions/setup-python` v6 -> v7 in `regression-tests.yml`. The bump landed in
  `ci.yml` only, so the other workflow was left behind.

### Changed

- Platform targets refreshed: `claude_code` 2.0.0 -> 2.1.263 and `cursor` 0.45.0 ->
  3.19.13 (validated), `codex` `latest_known` 0.40.0 -> 0.153.4 with `validated_against`
  left as `"unknown"` because nothing here was actually run against it. README badges
  regenerated to match.
- Claude model references moved from `claude-opus-4-8` to `claude-opus-5`
  (`config/config.example.toml`, AGENTS.md, stage4 synthesis docstring).
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
- CI runs the test job as a `3.11 / 3.12 / 3.13` matrix with `fail-fast: false`.
  Only 3.12 was ever exercised, so both ends of the supported range were untested.
  The legs roll up into the existing `CI` fan-in job, so the branch ruleset is
  unchanged.
- `ci.yml` and `regression-tests.yml` declare a `concurrency` group with
  `cancel-in-progress`, so a force-push stops racing its own superseded run for the
  required `CI` context. `release.yml` is deliberately excluded — cancelling a
  half-finished release is worse than a duplicate run.

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
