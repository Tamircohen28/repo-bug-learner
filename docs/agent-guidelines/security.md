# Security guidelines

Referenced from [AGENTS.md](../../AGENTS.md).

## Secrets

- Never commit `config/config.toml` or anything under `out/` — they may contain
  credentials or mined artifacts.
- Jira, GitHub, and Anthropic credentials come from environment variables
  (`JIRA_USER`, `JIRA_TOKEN`, `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`) — never hardcode
  them in source.
- The CI secret-scan job must stay green; do not disable it to land a change.

## External input

- Treat mined Jira/GitHub content as untrusted input. Do not `eval` or execute it.
- Synthesized rules are reviewed by a human before merge — never auto-merge rule PRs.

## Employer IP

- This is a personal repository. Never introduce employer-internal URLs, registry
  hosts, package names, or references.
