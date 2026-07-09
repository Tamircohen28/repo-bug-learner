# Platform equivalence

This app repo supports Claude Code, Cursor, and Codex with one canonical policy file.

| Concern | Claude Code | Cursor | Codex |
|---------|-------------|--------|-------|
| Canonical policy | `AGENTS.md` | `AGENTS.md` (via `.cursor/rules/000-project.mdc`) | `AGENTS.md` |
| Thin adapter | `CLAUDE.md` (`@AGENTS.md`) | `.cursor/rules/000-project.mdc` | — |
| Project skills | `.claude/skills/` | `.agents/skills/` (portable mirror) | `.agents/skills/` |
| Drift check | `make agent:check` | same | same |

## Skill bridge

Portable skills live under `.agents/skills/`. Claude Code project skills under
`.claude/skills/` mirror the same directory names. Keep both trees in sync when adding or
renaming skills.

Current skills: `repo-bug-review`.

Platform tool versions: [`docs/engineering/build-and-release/platform-targets.json`](../engineering/build-and-release/platform-targets.json).
