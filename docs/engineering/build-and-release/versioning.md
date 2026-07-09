# Versioning and release

This repo follows [Semantic Versioning](https://semver.org/). The declared version lives in
`pyproject.toml` (`version` field).

## Bump rules

| Bump | When |
|------|------|
| PATCH | Bug fixes, docs-only, non-breaking script tweaks |
| MINOR | Backward-compatible features — new rules, new skills, new docs |
| MAJOR | Breaking CLI flags, removed commands, incompatible config schema changes |

## Changelog

- Canonical history: [`docs/CHANGELOG.md`](../../CHANGELOG.md)
- Root mirror: [`CHANGELOG.md`](../../../CHANGELOG.md) (Keep-a-Changelog summary)

Update both under `[Unreleased]` before each release.

## Release checklist

1. Move `[Unreleased]` entries under `[X.Y.Z] - YYYY-MM-DD` in both changelogs
2. Bump `pyproject.toml` version
3. `git tag -a vX.Y.Z -m "vX.Y.Z"` and push the tag
4. Create a GitHub Release from changelog notes

## Validate

```bash
VER=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/')
git tag -l "v${VER}" | grep -q . || echo "missing tag v${VER}"
```
