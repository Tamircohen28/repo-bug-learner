#!/usr/bin/env bash
# Bootstrap script: full batch run for one target repo.
#
# Usage:
#   ./scripts/bootstrap.sh backend 2024-05-01
#
# Prerequisites:
#   - docker compose up -d                       (Postgres + pgvector running)
#   - config/config.toml filled in
#   - env vars set: JIRA_USER, JIRA_TOKEN, GITHUB_TOKEN, ANTHROPIC_API_KEY
#   - target service cloned to ./repos/<repo-name>
set -euo pipefail

REPO="${1:?usage: $0 <repo-name> <since-iso-date>}"
SINCE="${2:?usage: $0 <repo-name> <since-iso-date>}"

REPO_DIR="./repos/${REPO}"
if [[ ! -d "$REPO_DIR" ]]; then
  echo "Cloning ${REPO}..."
  mkdir -p ./repos
  GITHUB_ORG="${GITHUB_ORG:-your-org}"
  git clone "git@github.com:${GITHUB_ORG}/${REPO}.git" "$REPO_DIR"
fi

# Make sure the clone is up to date
git -C "$REPO_DIR" fetch --all --prune
git -C "$REPO_DIR" checkout master 2>/dev/null || git -C "$REPO_DIR" checkout main
git -C "$REPO_DIR" pull --ff-only

# Init schema if not already
python -m src.orchestrator schema

# Full pipeline. Drop --auto-ship for a first run to review candidates manually.
python -m src.orchestrator batch \
  --repo "$REPO" \
  --since "$SINCE" \
  --output "./out/${REPO}" \
  --repos-root ./repos

echo ""
echo "=== Bootstrap complete ==="
echo "Candidate rules: ./out/${REPO}/candidates/"
echo "Validation report: ./out/${REPO}/validated/report.json"
echo ""
echo "Next: review candidates, then run with --auto-ship to open PRs:"
echo "  python -m src.orchestrator ship --report ./out/${REPO}/validated/report.json"
