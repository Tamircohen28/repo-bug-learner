# Style guidelines

Referenced from [AGENTS.md](../../AGENTS.md).

## Python

- Python 3.11+. Lint and format with `ruff` (`make lint`).
- Prefer clear, minimal code. Do not add abstractions beyond what the task requires.
- Default to no comments; add one only when the "why" is non-obvious.

## Configuration

- Read org-specific values (Jira project, GitHub org, repo list, Claude base URL)
  from `config/config.toml`. Never hardcode them in source.

## Commits

- Imperative subject with optional scope: `feat: add go opengrep synthesis hints`.
- Keep commits scoped to one logical change.
