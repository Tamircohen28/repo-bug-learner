# repo-bug-learner CI Integration

Copy these workflows into any target repository to gate PRs with synthesized static-analysis rules.

## Setup

1. Copy workflow files from this directory into your repo's `.github/workflows/`.
2. Set repository variables or secrets:

| Variable | Required | Description |
|----------|----------|-------------|
| `RULES_REPO` | yes | GitHub `org/repo` slug of your Scalafix/Opengrep rules repository |
| `GITHUB_TOKEN` | yes | Token with `contents:read` on the rules repo |

3. Add `build.sbt` snippet from `../build.sbt.snippet` for Scala services (SemanticDB + Scalafix).

## Workflows

- `scalafix-pr.yml` — diff-aware Scalafix on PRs (new violations only)
- `opengrep-pr.yml` — diff-aware Opengrep/Semgrep on PRs
- `scalafix-full-scan.yml` — full-repo baseline scan (informational)
- `scalafix.yml` / `opengrep.yml` — standalone check jobs

Rules are fetched from `RULES_REPO` at CI runtime; no internal org defaults are baked in.
