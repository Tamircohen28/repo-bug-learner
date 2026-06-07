# Quick start

```bash
git clone https://github.com/TamirCohen28/repo-bug-learner.git
cd repo-bug-learner
docker compose up -d
uv sync --extra dev
cp config/config.example.toml config/config.toml
```

Fill in Jira URL, `project_key`, GitHub `org`, and `repos` list.

```bash
export JIRA_USER=... JIRA_TOKEN=... GITHUB_TOKEN=... ANTHROPIC_API_KEY=...
python -m src.orchestrator schema
python -m src.orchestrator batch --repo backend --since 2024-06-01 --output out/
```

Review `out/candidates/` then optionally:

```bash
python -m src.orchestrator ship --report out/validated/report.json
```
