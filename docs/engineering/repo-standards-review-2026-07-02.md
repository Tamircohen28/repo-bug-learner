# Repo standards review — repo-bug-learner

**Date:** 2026-07-02
**Target:** `/Users/tamircohen/Projects/repo-bug-learner`
**Profile:** app-gold

## Executive summary

The repo is in strong shape on core standards (S1–S7): README has banner, badges,
prerequisites, quick start, and license line; docs tree is complete (user +
engineering, ADRs, CHANGELOG, CONTRIBUTING); CI/CD workflows exist with a secret-scan
job; branch protection is enabled with 1 required approving review; CODEOWNERS and
dependabot are present. Employer (Wix) IP scan is CLEAN. The remaining gaps are almost
entirely in the multi-agent layer (L1–L7): no `AGENTS.md`, `CLAUDE.md` does not
reference `AGENTS.md`, no `.cursor/rules/`, no `docs/agent-guidelines/`, no
`agent:check`/validate command, and no agent-drift check. These are delegated to
`multi-agent-repo`.

## Severity summary

| Severity | Count |
|----------|-------|
| P1 | 4 |
| P2 | 4 (S4-01 CODEOWNERS is a false positive — file exists at `.github/CODEOWNERS`) |
| P3 | 0 |

## Standards gaps (S1–S7)

- **S4-01 (P2)** — CODEOWNERS flagged missing by inventory, but `.github/CODEOWNERS`
  exists (`* @TamirCohen28`). No action needed.

All other S1–S7 checks pass.

## Employer IP scan

CLEAN — no employer IP patterns found (scanned 2026-07-02).

## Multi-agent appendix

Gaps to be remediated by `multi-agent-repo` (phase 5 of polish):

- **L1-01 (P1)** — AGENTS.md missing at repo root
- **L2-02 (P1)** — CLAUDE.md does not reference AGENTS.md
- **L3-01 (P2)** — `.cursor/rules/` directory missing
- **L5-01 (P2)** — `docs/agent-guidelines/` missing
- **L6-03 (P1)** — No `agent:check` / validate command in Makefile
- **L6-04 (P1)** — CI exists but no documented agent validation command
- **L7-01 (P2)** — No check-agent-drift script

## Docs read-only notes

README and docs are well-structured and accurate. No content gaps identified in the
read-only pass. Quick Start is concrete and reproducible.

## Inventory appendix

```json
{"readme":{"has_badges":true,"has_prerequisites":true,"has_quick_start":true,"has_license_line":true,"has_banner":true},"docs":{"readme":true,"changelog":true,"contributing":true,"user_dir":true,"engineering_dir":true},"github":{"ci_workflow":true,"secret_scan_job":true,"pr_template":true,"dependabot":true},"root_files":{"license":true,"codeowners":"present at .github/CODEOWNERS","gitignore":true,"claude_md":true,"agents_md":false},"branch_governance":{"protection_enabled":true,"required_approving_reviews":1},"hygiene":{"self_hosted_ci":false}}
```

## Next steps

1. Create `feat/repo-standards-setup` branch.
2. Phase 5: run `multi-agent-repo` to add AGENTS.md, `.cursor/rules/`, agent
   guidelines, `agent:check` command, and CI validation.
3. Open PR; drive to green via `pr-dev`.
