<p align="center">
  <img src="assets/banner.png" alt="repo-bug-learner — mine bugs, synthesize rules" width="900"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/CI-GitHub%20Actions-blue" alt="CI"/>
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License"/>
</p>

# repo-bug-learner

Mine historical bug-fix commits from Jira + GitHub, cluster recurring patterns, synthesize **Scalafix** (Scala) and **Opengrep** (TypeScript, JavaScript, Python, Go) rules, validate them against a held-out corpus, and ship them as PRs to a rules repository that gates future PRs via CI.

## Feature highlights

- **Language-aware synthesis** — Scala clusters become Scalafix rules; TS/JS/Python/Go clusters become Opengrep YAML rules
- **Configurable mining** — any Jira project + GitHub org; ticket pattern and repo list in `config.toml`
- **Validation loop** — precision/recall thresholds before auto-shipping rules
- **PR review skill** — Claude Code skill at `.claude/skills/repo-bug-review/` for scanning local code or GitHub PRs
- **CI templates** — copy workflows from `service-integration/` into any target repo
- **Continuous learning** — batch bootstrap plus optional per-bug continuous loop

## Prerequisites

- Python 3.11+
- Docker (Postgres + pgvector via `docker compose up -d`)
- [uv](https://github.com/astral-sh/uv) or pip
- Jira + GitHub API credentials
- Anthropic API key (or compatible endpoint)

## Quick Start

```bash
docker compose up -d
uv sync --extra dev
cp config/config.example.toml config/config.toml
# Edit config.toml — Jira URL, GitHub org, repos, Claude base_url

export JIRA_USER=... JIRA_TOKEN=... GITHUB_TOKEN=... ANTHROPIC_API_KEY=...

python -m src.orchestrator schema

python -m src.orchestrator batch \
  --repo backend \
  --since 2024-05-01 \
  --output out/

ls out/candidates/
make test
```

## Documentation

See [docs/README.md](docs/README.md) for the full doc map.

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
