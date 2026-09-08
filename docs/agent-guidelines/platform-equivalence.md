# Platform equivalence

This app repo supports Claude Code, Cursor, and Codex with one canonical policy file.

| Concern | Claude Code | Cursor | Codex |
|---------|-------------|--------|-------|
| Canonical policy | `AGENTS.md` | `AGENTS.md` (via `.cursor/rules/000-project.mdc`) | `AGENTS.md` |
| Thin adapter | `CLAUDE.md` (`@AGENTS.md`) | `.cursor/rules/000-project.mdc` | — |
| Project skills | `.claude/skills/` (generated mirror) | `.agents/skills/` (canonical) | `.agents/skills/` (canonical) |
| Drift check | `make agent:check` | same | same |

## Skill bridge

`.agents/skills/` is canonical. Claude Code only discovers skills under `.claude/skills/`,
so that tree is a **generated mirror** of it — edit the canonical copy and regenerate:

```bash
make skill-bridge         # regenerate .claude/skills from .agents/skills
make skill-bridge-check   # assert they match (runs inside `make agent:check`)
```

The mirror is a real copy rather than a symlink because `check-feature-equivalence.sh`
locates skill directories with `find -type d`, which does not match a symlink. That makes
the copy the only workable shape, and `skill-bridge-check` is what keeps it honest: before
it existed the two trees could diverge with the whole gate still green.

Current skills: `repo-bug-review`.

## Capability registry

[`core/capabilities/platforms.json`](../../core/capabilities/platforms.json) is the single
source of truth for what each supported surface can actually do. It is rooted at the
platform (Claude, Cursor, Codex) with one entry per runtime surface underneath, because
install path and capabilities differ per surface. Every supported surface answers every
capability key — an omitted key is a schema error, so a gap cannot hide behind silence —
and nothing is claimed `native` without a validation command that proves it. Surfaces
nobody has measured are marked `unverified` and carry no capability claims at all.

Validate it against its schema after editing:

```bash
uv run --with jsonschema python -c "import json,jsonschema; \
  jsonschema.Draft202012Validator(json.load(open('core/capabilities/schema.json'))) \
  .validate(json.load(open('core/capabilities/platforms.json')))"
```

Platform tool versions: [`docs/engineering/build-and-release/platform-targets.json`](../engineering/build-and-release/platform-targets.json),
whose targets each name the platform the registry files them under.
