#!/usr/bin/env bash
# sync-skill-bridge.sh — regenerate (or assert) the .claude/skills mirror.
#
# Usage:
#   sync-skill-bridge.sh [repo-root]            # regenerate .claude/skills from .agents/skills
#   sync-skill-bridge.sh [repo-root] --check    # assert the mirror matches; exit 1 on drift
#   sync-skill-bridge.sh -h | --help
#
# .agents/skills is the canonical, platform-neutral skill payload. Claude Code only
# discovers skills under .claude/skills, so that directory is a mirror of it.
#
# A symlink would make divergence impossible, but check-feature-equivalence.sh finds
# skill directories with `find -type d`, which does not match a symlink — the bridge
# would read as empty and the equivalence check would fail. So the mirror stays a real
# copy and this script is what keeps it honest: nothing else compared the two, and a
# copy nobody compares is a copy that drifts.
#
# Exit 0 when the mirror matches (or was regenerated); 1 on drift under --check.
set -euo pipefail

usage() { sed -n '2,18p' "$0" | sed -E 's/^# ?//'; exit "${1:-0}"; }
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then usage 0; fi

ROOT="."
CHECK=false
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=true ;;
    --*) ;;
    *) ROOT="$arg" ;;
  esac
done
ROOT="$(cd "$ROOT" && pwd)"

SRC="$ROOT/.agents/skills"
DEST="$ROOT/.claude/skills"

if [[ ! -d "$SRC" ]]; then
  echo "ERROR: $SRC does not exist — there is no canonical skill payload to mirror" >&2
  exit 1
fi

if [[ "$CHECK" == true ]]; then
  if [[ ! -d "$DEST" ]]; then
    echo "ERROR: .claude/skills is missing — run: make skill-bridge" >&2
    exit 1
  fi
  if ! diff -r "$SRC" "$DEST" >/dev/null 2>&1; then
    echo "ERROR: .claude/skills has drifted from .agents/skills — run: make skill-bridge" >&2
    diff -r "$SRC" "$DEST" >&2 || true
    exit 1
  fi
  echo "Skill bridge check passed (.claude/skills matches .agents/skills)"
  exit 0
fi

rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -R "$SRC" "$DEST"
echo "Regenerated .claude/skills from .agents/skills"
