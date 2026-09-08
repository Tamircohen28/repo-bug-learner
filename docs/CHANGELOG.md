# Changelog

All notable changes to this project will be documented in this file.

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
