# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

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
