@AGENTS.md

# CLAUDE.md — Claude-only addenda

All shared policy, commands, and constraints live in [AGENTS.md](AGENTS.md) — the
canonical source of truth. Only Claude Code-specific notes belong here.

## Skills

- `.claude/skills/repo-bug-review/` — review a file, directory, or GitHub PR against
  the synthesized rule set. Invoke when asked to review/scan/audit code for known bug
  patterns.

## Commit convention

Imperative subject, optional scope: `feat: add go opengrep synthesis hints`.
