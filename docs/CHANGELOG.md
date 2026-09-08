# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed

- The semgrep install no longer assumes the venv has pip. `uv sync` builds `.venv`
  without pip, so `make test` on a checkout that had run `make install` died on
  `make: .venv/bin/pip: No such file or directory`. It now prefers `uv pip install`,
  falls back to the venv's own pip, and bootstraps pip via `ensurepip` only as a last
  resort. CI never hit this because `actions/setup-python` + `python -m venv` does
  ship pip.
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

- `uv.lock` is now tracked. Every runtime dependency in `pyproject.toml` is declared
  as a lower bound with no ceiling, so two `make install` runs on different days
  could resolve to different versions with nothing recording which one was tested.
  This repo has already paid for that once — an unpinned ruff turned a green CI red
  on an unchanged tree. Verified with `uv lock --check` (73 packages, consistent
  with pyproject) and a `uv sync --frozen` install that runs the suite green.
- `core/capabilities/platforms.json` + `schema.json` — the single source of truth for
  what each supported agent surface (Claude Code, Cursor, Codex) can actually do.
  Every supported surface answers all 19 capability keys, nothing is claimed `native`
  without a validation command, and unmeasured surfaces (Claude Desktop, Cursor CLI,
  Codex IDE) are recorded as `unverified` with no capability claims rather than
  invented ones.
- `make skill-bridge` / `make skill-bridge-check` — `.claude/skills` is now a
  generated mirror of the canonical `.agents/skills`, asserted by `make agent:check`.
  The two trees were hand-copied and could diverge with the whole gate still green.

- Renamed project to `repo-bug-learner` with generic Jira/GitHub configuration
- Multi-language Opengrep synthesis for Python and Go
- Example Opengrep rules: `py-mutable-default-arg`, `py-bare-except`, `go-ignored-error`, `go-defer-in-loop`
- Full docs tree, CI workflows, and Claude Code skill `repo-bug-review`

### Changed

- CLI renamed from `bbl` to `rbl`; `--service` flag is now `--repo`
- **`claude-opus-4-8`** is now the default `model_strong` in `config.example.toml` (was `claude-opus-4-7`)
- Synthesis calls (`ClaudeClient.strong`) now use adaptive thinking, `xhigh` effort, and streaming — faster and higher quality on complex rule synthesis tasks
- Prompt caching added to synthesis system prompts (auto-activates when `project_context` exceeds 4096 tokens)
- Retry logic narrowed to network-level failures only; the SDK handles 429/5xx automatically via `max_retries=3`
- Cache token usage (`cache_read_input_tokens`, `cache_creation_input_tokens`) now tracked in `ClaudeResponse`
- `anthropic` SDK minimum bumped to `>=0.52.0`
