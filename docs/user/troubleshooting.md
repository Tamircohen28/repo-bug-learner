# Troubleshooting

## Jira mining returns zero bugs

Check `jql_template`, `project_key`, and that bugs are in Done/Closed/Resolved after `--since`.

## No PRs linked to bugs

Verify `github.org` and `github.repos` match your org. Adjust `jira.ticket_pattern` if ticket keys differ from `PROJ-123`.

## Scalafix synthesis skipped

Clusters need at least two Scala entries. Mixed-language clusters route to Opengrep.

## Postgres connection refused

Run `docker compose up -d` and confirm `postgres.database = rbl` in config matches docker-compose.

## Semgrep precision check fails in CI

Add or fix positive/negative snippets under `rule-validator/rules/tests/`.
