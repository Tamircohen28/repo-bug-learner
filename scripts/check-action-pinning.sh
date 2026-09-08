#!/usr/bin/env bash
# check-action-pinning.sh — fail when a workflow trusts a mutable action ref.
#
# WHY THIS EXISTS
#   `uses: actions/checkout@v7` does not name a version. It names a tag, and a
#   tag is a pointer the action's owner can move at any time — `v7` pointed at
#   v7.0.0 when a workflow was written and at v7.0.1 a week later, with no commit
#   in this repository and no PR to review. That is a third party's write access
#   to this repo's CI, and the whole point of `permissions:` blocks and secret
#   scanning is undone by it. A 40-character commit SHA is immutable; the
#   `# v7.0.0` comment beside it is what keeps it readable, and what Dependabot
#   rewrites when it proposes a bump.
#
#   Every ref in this repository was a movable tag until this check existed —
#   the standard was practised rather than checked, which is the same failure
#   mode as a validator nobody runs.
#
#   `service-integration/.github/workflows/` matters more than this repo's own CI.
#   Those files are templates: they are copied wholesale into a service repository
#   to wire up its opengrep / scalafix / scapegoat scans, so an unpinned `uses:`
#   there is not one repo's problem — it is the default every consuming repo
#   inherits, in a workflow that holds `security-events: write`.
#
#   `uses:` is not the only way a workflow runs someone else's code. A job-level
#   `container:` and a `services.*.image:` are pulled at job start and everything
#   in the job executes inside them, holding the job's own permissions. Scanning
#   only `uses:` reports a fully pinned workflow while a `:latest` tag decides what
#   runs next to `security-events: write` — the checker's verdict decided by where
#   it looked rather than by what is true. Both forms are checked here.
#
# WHAT COUNTS AS PINNED
#   uses: owner/repo@<40 hex>              — pinned
#   uses: owner/repo@<40 hex> # v7.0.0     — pinned, and readable. Preferred.
#   uses: owner/repo@v7                    — NOT pinned: a movable tag
#   uses: owner/repo@main                  — NOT pinned: a branch
#   container: name@sha256:<64 hex>        — pinned
#   container: name:v1.2.3                 — NOT pinned: a movable tag
#   container: name:latest                 — NOT pinned, and the worst case
#
# WHAT IS EXEMPT, AND WHY
#   ./path            a local action in this same repository — it moves only when
#                     this repo moves, so there is nothing external to pin.
#   docker://...      reported, not failed: a digest-pinned image is the right fix
#                     but the syntax is different and none exist here today.
#   A line carrying   action-pin-ok: <reason>   — an explicit, readable waiver.
#                     A path-shaped carve-out is how the mutable ref creeps back.
#
# Usage: check-action-pinning.sh [<repo_root>] [--self-test]
# Exit:  0 clean · 1 mutable refs found · 2 usage/environment
set -uo pipefail

ROOT="."
SELF_TEST=0
for arg in "$@"; do
  case "$arg" in
    --self-test) SELF_TEST=1 ;;
    # Print the whole header block, however long it grows. A fixed line range is
    # the same defect this script exists to catch: a gate on where to look rather
    # than on what is true -- it silently truncated --help the moment the header
    # gained a paragraph.
    -h|--help) awk 'NR>1 && /^#/ {sub(/^#[ ]?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;;
    -*) echo "check-action-pinning.sh: unknown option '$arg'" >&2; exit 2 ;;
    *) ROOT="$arg" ;;
  esac
done

# is_hex <string> <length> — true when the string is exactly <length> lowercase
# hex characters. A digest is 64; an action SHA is 40.
is_hex() {
  case "$1" in ''|*[!0-9a-f]*) return 1 ;; esac
  [ "${#1}" -eq "$2" ]
}

# scan <dir> — every "path:line:ref" whose ref is not a 40-hex SHA, plus every
# container image whose ref is not a digest.
# Prints nothing when clean. Never fails the shell; the caller decides.
scan() {
  local dir="$1" f line n ref kind
  [ -d "$dir" ] || return 0
  while IFS= read -r f; do
    n=0
    while IFS= read -r line; do
      n=$((n + 1))
      case "$line" in *action-pin-ok:*) continue ;; esac
      # A whole-line comment is prose, not configuration. Stripping the trailing
      # `#...` is not enough: a line that *begins* with `#` still matches
      # `*container:*`, so the checker flagged the comment explaining why a
      # container had been removed. Found by running it on that very commit.
      case "${line#"${line%%[![:space:]]*}"}" in '#'*) continue ;; esac
      # `uses:` / `container:` / `image:` value, quotes and inline comment stripped.
      case "$line" in
        *uses:*)      ref="${line#*uses:}";      kind=uses  ;;
        *container:*) ref="${line#*container:}"; kind=image ;;
        *image:*)     ref="${line#*image:}";     kind=image ;;
        *) continue ;;
      esac
      ref="${ref%%#*}"
      ref="$(printf '%s' "$ref" | tr -d " \"'" )"
      [ -n "$ref" ] || continue

      # A `container:` or `services.*.image:` is pulled at job start and runs with
      # the job's own permissions -- `security-events: write` in at least one of
      # these templates. A moving tag there is a third party choosing what executes
      # next to the token. Only a digest pins it, and `uses:`-only scanning cannot
      # see any of it: this whole class was unchecked until it was looked for.
      if [ "$kind" = image ]; then
        case "$ref" in
          *@sha256:*) is_hex "${ref##*@sha256:}" 64 && continue ;;
        esac
        printf '%s:%s:%s (container image — pin by digest: name@sha256:<64 hex>)\n' "$f" "$n" "$ref"
        continue
      fi
      case "$ref" in
        ./*|.\\*) continue ;;                    # local action: nothing external
        docker://*) printf '%s:%s:%s (docker ref — pin by digest)\n' "$f" "$n" "$ref"; continue ;;
      esac
      case "$ref" in
        *@*) : ;;
        *) printf '%s:%s:%s (no ref at all)\n' "$f" "$n" "$ref"; continue ;;
      esac
      case "${ref##*@}" in
        [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) : ;;
        *) printf '%s:%s:%s\n' "$f" "$n" "$ref" ;;
      esac
    done < "$f"
  done < <(find "$dir" \( -name '*.yml' -o -name '*.yaml' \) -type f 2>/dev/null | sort)
}

# --- positive control ------------------------------------------------------
# A checker that has never been shown to fail is indistinguishable from one that
# cannot. This builds both a violating workflow and its corrected twin.
self_test() {
  local tmp rc=0 out
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN
  mkdir -p "$tmp/bad" "$tmp/good"

  cat > "$tmp/bad/w.yml" <<'YML'
jobs:
  a:
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-node@main
      - uses: ./.github/actions/local
      - uses: some/act@1111111111111111111111111111111111111111 # v1.2.3
      - uses: waived/act@v2 # action-pin-ok: vendor publishes no SHA
  b:
    container: some/img:latest
  c:
    container: some/img@sha256:2222222222222222222222222222222222222222222222222222222222222222
  d:
    services:
      db:
        image: postgres:16
  # A comment naming `container: commented/img:latest` is prose about a change,
  # not a job that pulls anything.
YML
  out="$(scan "$tmp/bad")"
  [ "$(printf '%s\n' "$out" | grep -c 'checkout@v7')" = 1 ] \
    || { echo "  self-test: movable tag not caught" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'setup-node@main')" = 1 ] \
    || { echo "  self-test: branch ref not caught" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'actions/local')" = 0 ] \
    || { echo "  self-test: local action wrongly flagged" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'some/act')" = 0 ] \
    || { echo "  self-test: SHA-pinned ref wrongly flagged" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'waived/act')" = 0 ] \
    || { echo "  self-test: action-pin-ok waiver ignored" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'some/img:latest')" = 1 ] \
    || { echo "  self-test: mutable container: tag not caught" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'some/img@sha256')" = 0 ] \
    || { echo "  self-test: digest-pinned container wrongly flagged" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'postgres:16')" = 1 ] \
    || { echo "  self-test: services.*.image: not caught" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'commented/img')" = 0 ] \
    || { echo "  self-test: comment line wrongly flagged" >&2; rc=1; }

  cat > "$tmp/good/w.yml" <<'YML'
jobs:
  a:
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
  b:
    container: some/img@sha256:2222222222222222222222222222222222222222222222222222222222222222
YML
  [ -z "$(scan "$tmp/good")" ] \
    || { echo "  self-test: corrected workflow still flagged" >&2; rc=1; }

  [ "$rc" -eq 0 ] && echo "  self-test passed (detector fires, and goes quiet when fixed)"
  return "$rc"
}

if [ "$SELF_TEST" -eq 1 ]; then
  self_test || exit 1
fi

cd "$ROOT" 2>/dev/null || { echo "check-action-pinning.sh: no such directory: $ROOT" >&2; exit 2; }

# This repo's own CI, and every workflow template copied into a service repository.
findings="$( { scan ".github/workflows"; scan "service-integration/.github/workflows"; } )"

if [ -n "$findings" ]; then
  echo "  mutable action refs — pin to a 40-char commit SHA with a '# <version>' comment:" >&2
  printf '%s\n' "$findings" | sed 's/^/    /' >&2
  echo "  resolve an action:    gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq .object.sha" >&2
  echo "  resolve a container: docker buildx imagetools inspect <image>:<tag> | head -2" >&2
  exit 1
fi

echo "  all action refs are SHA-pinned and all container images are digest-pinned"
