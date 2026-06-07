# repo-bug-learner — Claude Code guide

## Overview

Python pipeline that mines Jira bugs + GitHub fix PRs, clusters bug patterns with pgvector, synthesizes Scalafix/Opengrep rules via Claude, validates them, and opens PRs to rules repos.

## Key paths

| Path | Purpose |
|------|---------|
| `src/orchestrator.py` | CLI entry (`rbl`) — batch, ship, schema |
| `src/stage1_mine/` | Jira/GitHub mining + SZZ labeling |
| `src/stage4_synthesize/` | LLM rule synthesis |
| `src/stage5_validate/` | Precision/recall validation |
| `rule-validator/` | Scalafix rule harness + Opengrep YAML |
| `scripts/scan_repo.py` | Fast repo scanner + review backend |
| `scripts/review.py` | Review orchestrator for the Claude skill |
| `config/config.example.toml` | Configuration template |

## Commands

```bash
make install   # uv sync --extra dev
make test      # scan regression + pytest
make lint      # ruff
docker compose up -d
python -m src.orchestrator batch --repo backend --since 2024-01-01
```

## Commit convention

Imperative subject, optional scope: `feat: add go opengrep synthesis hints`

## Hard constraints

- Never commit `config/config.toml` or `out/` (local artifacts)
- Never hardcode org-specific URLs in source — use config
- Do not auto-merge synthesized rules; human review is required
- Scalafix rules target Scala 2.12 syntax only
