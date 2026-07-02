# Repo standards remediation plan — repo-bug-learner

**Date:** 2026-07-02
**Source review:** `repo-standards-review-2026-07-02.md`

## Phase 0 — IP scan
CLEAN. No action.

## Phases 1–4 — Standards (S1–S7)
No action required. README banner/badges/prereqs/quick-start, docs tree, CI/CD with
secret-scan, branch protection (1 review), CODEOWNERS, and dependabot all present.

## Phase 5 — Multi-agent layer (delegated to `multi-agent-repo`)
Remediates all P1/P2 multi-agent gaps on branch `feat/repo-standards-setup`:
- AGENTS.md at repo root (L1-01)
- CLAUDE.md → AGENTS.md reference (L2-02)
- `.cursor/rules/` (L3-01)
- `docs/agent-guidelines/` (L5-01)
- `agent:check` command in Makefile (L6-03)
- CI agent-validation step (L6-04)
- check-agent-drift script (L7-01)

## Phase 6 — Docs
No P1 docs findings. Skip.

## Phase 7 — Assert contract
`assert-contract.sh` must show P1/P2/P3 = 0, then open PR.
