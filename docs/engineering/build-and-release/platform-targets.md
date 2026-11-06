# Platform target versions

Machine-readable source: [`platform-targets.json`](platform-targets.json).

| Platform | Min supported | Validated against | Latest known |
|----------|---------------|-------------------|--------------|
| Claude Code | 2.0.0 | 2.1.318 | 2.1.318 |
| Cursor | 0.45.0 | 3.29.9 | 3.29.9 |
| Codex | 0.40.0 | 0.167.0 | 0.167.0 |

Last reviewed 2026-11-06 with `tamirs-superpowers:platform-sync`. "Validated against" means
the upstream changelog and the instruction-file docs (`CLAUDE.md` `@`-imports, `AGENTS.md`
discovery, `.cursor/rules/*.mdc` frontmatter, project skills) were reviewed up to that
version and no breaking change touched what this repo uses. Cursor publishes no version
numbers in its changelog, so its row is the desktop build the review ran against.

Update this file and the README platform badges whenever the targets are re-reviewed.
Agents run `make platform-targets-sync` (refreshes `latest_known` for Claude Code and
Codex from npm / GitHub releases) and `make platform-targets-assert` before release.
