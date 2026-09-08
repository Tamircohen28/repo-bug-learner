# AGENTS.md — repo-bug-learner

Canonical agent instructions for this repository. Tool-specific files
(`CLAUDE.md`, `.cursor/rules/*.mdc`) are thin adapters that point here — this file
is the single source of truth.

## Overview

Python pipeline that mines Jira bugs + GitHub fix PRs, clusters bug patterns with
pgvector, synthesizes Scalafix (Scala) and Opengrep (TS/JS/Python/Go) rules via
Claude, validates them against a held-out corpus, and opens PRs to rules repos that
gate future PRs via CI.

## Commands

```bash
make install   # uv sync --extra dev
make update    # refresh deps after pulling main
make uninstall # remove venv + caches
make test      # precision check + regression scan + pytest
make lint      # ruff check src scripts
make precision # precision_check.py (semgrep)
make agent:check           # drift + feature equivalence + platform targets + skill bridge
make skill-bridge          # regenerate .claude/skills from canonical .agents/skills
make repo-standards-gate   # agent polish + contract assert (pre-PR)
make schema    # initialize DB schema
docker compose up -d   # Postgres + pgvector
python -m src.orchestrator batch --repo backend --since 2024-01-01
```

## Working agreements

- Form a hypothesis, apply one change, verify it, then repeat. Do not batch unrelated
  changes.
- Before claiming a task done, run the relevant command (`make test` / `make lint`)
  and cite the result. Never claim success without evidence.
- Keep changes minimal and scoped to the task. Do not refactor or add abstractions
  beyond what the task requires.
- Default to no code comments; add one only when the "why" is non-obvious.

## Repository expectations

- **Language:** Python 3.11+. Lint with `ruff`. Format follows `ruff` defaults.
- **Config over hardcoding:** never hardcode org-specific URLs, Jira projects, or
  repo lists in source — read them from `config/config.toml`.
- **Human review required:** do not auto-merge synthesized rules. A person must
  approve rule PRs.
- **Scalafix rules target Scala 2.12 syntax only.**

## Claude API notes

- Default `model_strong` is `claude-opus-5` with adaptive thinking + `xhigh` effort
  + streaming. Opus 5 thinks by default; the call still passes
  `{"type": "adaptive"}` explicitly so it stays correct on 4.8, where omitting it
  means no thinking at all.
- `model_fast` is `claude-haiku-4-5` — no thinking, no effort param (unsupported on
  Haiku).
- Do NOT add `temperature`, `top_p`, or `budget_tokens` to Opus 5 calls — all
  three return a 400 on 4.7 and later.
- The SDK retries 429/5xx automatically; tenacity covers connection failures only.

## Key files

| Path | Purpose |
|------|---------|
| `src/orchestrator.py` | CLI entry (`rbl`) — batch, ship, schema |
| `src/stage1_mine/` | Jira/GitHub mining + SZZ labeling |
| `src/stage4_synthesize/` | LLM rule synthesis |
| `src/stage5_validate/` | Precision/recall validation |
| `rule-validator/` | Scalafix rule harness + Opengrep YAML |
| `scripts/scan_repo.py` | Fast repo scanner + review backend |
| `config/config.example.toml` | Configuration template |
| `core/capabilities/platforms.json` | What each supported agent surface can do |

## Versioning

See [docs/engineering/build-and-release/versioning.md](docs/engineering/build-and-release/versioning.md).
Update `docs/CHANGELOG.md` and root `CHANGELOG.md` under `[Unreleased]` before each release.

## Detailed guidelines

- [Testing](docs/agent-guidelines/testing.md)
- [Security](docs/agent-guidelines/security.md)
- [Style](docs/agent-guidelines/style.md)
- [Platform equivalence](docs/agent-guidelines/platform-equivalence.md)

## Off-limits

- Never commit `config/config.toml` or `out/` (local artifacts, may hold secrets).
- Never commit credentials or API keys (Jira, GitHub, Anthropic).
- Never introduce employer-internal URLs, registries, or references.
