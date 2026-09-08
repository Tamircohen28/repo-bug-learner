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
#   Which is exactly why this no longer scans a list of directories. The first
#   version named the two roots its author remembered; a root nobody thought of
#   is invisible to it, and it reports "all refs are SHA-pinned" while unpinned
#   refs sit in a file it never opened. It now walks the whole repository. A
#   checker must not decide its verdict by where it happened to look.
#
# WHAT IS SCANNED
#   Every *.yml, *.yaml, *.tmpl and *.md in the tree (.git, node_modules and
#   .venv pruned). `.tmpl` because a scaffold template is a workflow before it is
#   rendered; `.md` because documentation carries real workflow bodies in fenced
#   blocks -- and ONLY fenced blocks there, since prose about a mutable ref is
#   not a mutable ref. `uses:`, `container:` and `image:` are matched as YAML
#   keys beginning the line, never as substrings: `**...and their causes:**`
#   is a sentence, not a step.
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
#   docker://...@sha256:<64 hex>
#                     a digest-pinned image — immutable, same guarantee as a
#                     commit SHA, so it passes. Any other docker ref
#                     (`docker://img:v1`, `docker://img:latest`) is a movable
#                     tag and FAILS. It is not exempt; this header said
#                     "reported, not failed" from #18 onward while the code
#                     reported unconditionally and every finding exits 1 — so a
#                     correctly digest-pinned ref was told to pin by digest. A
#                     check whose correction does not clear it is what drives
#                     someone to add the path-shaped carve-out warned about
#                     below.
#   action-pin-ok:    an explicit, readable waiver — but only in the comment part
#                     of the line, after a `#`. A path-shaped carve-out is how the
#                     mutable ref creeps back; a waiver that matches anywhere on
#                     the line lets an image called `owner/action-pin-ok` waive
#                     itself.
#
# Usage: check-action-pinning.sh [<repo_root>] [--self-test]
# Exit:  0 clean · 1 mutable refs found · 2 usage/environment
set -uo pipefail

ROOT="."
SELF_TEST=0
# Resolved before any cd, because the self-test re-invokes this script.
case "$0" in /*) SELF="$0" ;; *) SELF="$PWD/$0" ;; esac
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
  local dir="$1" f line trimmed n ref kind md fence digest
  [ -d "$dir" ] || return 0
  while IFS= read -r f; do
    n=0; fence=0
    case "$f" in *.md) md=1 ;; *) md=0 ;; esac
    while IFS= read -r line; do
      n=$((n + 1))
      trimmed="${line#"${line%%[![:space:]]*}"}"

      # In Markdown, only fenced blocks are configuration; everything else is
      # prose ABOUT configuration. Without this, CHANGELOG.md's own entry
      # explaining that `uses: actions/checkout@v7` names a movable tag is
      # reported as a movable tag.
      if [ "$md" -eq 1 ]; then
        case "$trimmed" in '```'*|'~~~'*) fence=$((1 - fence)); continue ;; esac
        [ "$fence" -eq 1 ] || continue
      fi

      # The waiver must live in a comment, not merely somewhere on the line.
      # `*action-pin-ok:*` is the same substring match that made `causes:` parse
      # as a step: an action or image whose own name carries the token -- say
      # `uses: owner/action-pin-ok@v1` -- would waive itself and never be
      # reported. Only the text after the first `#` can waive.
      case "$line" in
        *'#'*) case "${line#*#}" in *action-pin-ok:*) continue ;; esac ;;
      esac
      # A whole-line comment is prose, not configuration. Stripping the trailing
      # `#...` is not enough: a line that *begins* with `#` still matches
      # `*container:*`, so the checker flagged the comment explaining why a
      # container had been removed. Found by running it on that very commit.
      case "$trimmed" in '#'*) continue ;; esac
      # `uses:` / `container:` / `image:` must be the YAML key, not a substring.
      # Globbing *uses:* anywhere on the line makes "**Common errors and their
      # causes:**" parse as a step -- ca-uses:. Strip the sequence dash, then
      # require the key to BEGIN the line. Found by running this against the
      # tree, not against the fixtures.
      case "$trimmed" in '- '*) trimmed="${trimmed#- }"; trimmed="${trimmed#"${trimmed%%[![:space:]]*}"}" ;; esac
      case "$trimmed" in
        uses:*)      ref="${trimmed#uses:}";      kind=uses  ;;
        container:*) ref="${trimmed#container:}"; kind=image ;;
        image:*)     ref="${trimmed#image:}";     kind=image ;;
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
        # A docker image is pinned the same way an action is, by an immutable
        # identifier; only the syntax differs (`@sha256:<64 hex>`, not a
        # 40-char commit SHA). Route it through that test rather than
        # reporting every docker ref -- an unconditional report fails a ref
        # that is already correct, and tells you to do the thing you just did.
        docker://*)
          digest="${ref##*@sha256:}"
          if [ "$digest" != "$ref" ] && [ ${#digest} -eq 64 ] \
             && [ -z "$(printf '%s' "$digest" | tr -d 'a-f0-9')" ]; then
            continue
          fi
          printf '%s:%s:%s (docker ref — pin by @sha256:<digest>)\n' "$f" "$n" "$ref"
          continue ;;
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
  done < <(find "$dir" \( -name .git -o -name node_modules -o -name .venv \) -prune -o \
           \( -name '*.yml' -o -name '*.yaml' -o -name '*.tmpl' -o -name '*.md' \) \
           -type f -print 2>/dev/null | sort)
}

# --- positive control ------------------------------------------------------
# A checker that has never been shown to fail is indistinguishable from one that
# cannot. This builds both a violating workflow and its corrected twin.
self_test() {
  local tmp rc=0 out planted_rc
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
      - uses: docker://ghcr.io/owner/action-pin-ok:v1
      - uses: docker://ghcr.io/owner/pinned@sha256:2222222222222222222222222222222222222222222222222222222222222222
      - uses: docker://ghcr.io/owner/shortdigest@sha256:abc123
  e:
    container: owner/action-pin-ok:latest
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
  [ "$(printf '%s\n' "$out" | grep -c 'owner/action-pin-ok')" = 2 ] \
    || { echo "  self-test: waiver token in the ref itself waived the line" >&2; rc=1; }
  # The docker branch used to print unconditionally, so a ref that is already
  # digest-pinned was reported and told to pin by digest. A check whose own
  # correction does not clear it teaches people to carve out a path instead.
  [ "$(printf '%s\n' "$out" | grep -c 'owner/pinned')" = 0 ] \
    || { echo "  self-test: digest-pinned docker ref wrongly flagged" >&2; rc=1; }
  # ...and the digest test must be the real one: 64 lowercase hex, not merely
  # the presence of the literal '@sha256:'. A truncated digest is not a pin.
  [ "$(printf '%s\n' "$out" | grep -c 'owner/shortdigest')" = 1 ] \
    || { echo "  self-test: truncated docker digest accepted as a pin" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'docker ref')" = 2 ] \
    || { echo "  self-test: docker findings not reported as docker refs" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'some/img:latest')" = 1 ] \
    || { echo "  self-test: mutable container: tag not caught" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'some/img@sha256')" = 0 ] \
    || { echo "  self-test: digest-pinned container wrongly flagged" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'postgres:16')" = 1 ] \
    || { echo "  self-test: services.*.image: not caught" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'commented/img')" = 0 ] \
    || { echo "  self-test: comment line wrongly flagged" >&2; rc=1; }

  # --- cases the fixtures did not have, and the real tree did -----------------
  # Every one of these was a live defect: a substring match reading a sentence as
  # a step, a root list that never opened the file, and prose about a mutable ref
  # reported as a mutable ref once .md came into scope.
  cat > "$tmp/bad/prose.md" <<'MD'
- `uses: actions/checkout@v7` names a tag, not a version. Do not copy this line.
A doc may also show the bare key in prose, like so:

uses: prose/unfenced@v2

and a job container in prose, like so:

container: prose/unfenced-img:latest

```yaml
      - uses: prose/fenced@v9
    container: prose/fenced-img:latest
```
MD
  cat > "$tmp/bad/sub.yml" <<'YML'
# comment mentioning uses: commented/out@v3 which is not a step
steps:
  - name: notes
    run: echo "**Common errors and their causes:**"
  - name: more notes
    run: echo "the runner-image: ubuntu-latest is not an image: key"
YML
  cat > "$tmp/bad/t.yml.tmpl" <<'TMPL'
jobs:
  a:
    container: tmpl/img:latest
    steps:
      - uses: tmpl/act@v1
TMPL
  out="$(scan "$tmp/bad")"
  [ "$(printf '%s\n' "$out" | grep -c 'checkout@v7')" = 1 ] \
    || { echo "  self-test: markdown PROSE wrongly flagged (or bad/w.yml missed)" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'prose/fenced@v9')" = 1 ] \
    || { echo "  self-test: fenced markdown block not scanned" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'prose/fenced-img')" = 1 ] \
    || { echo "  self-test: fenced markdown container: not scanned" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'prose/unfenced')" = 0 ] \
    || { echo "  self-test: unfenced markdown prose read as configuration" >&2; rc=1; }
  # sub.yml contains NO step at all: a YAML comment naming a ref, a run: line
  # ending in "causes:", and a run: line containing "-image:". Any finding from it
  # is a false positive, whatever it says -- assert on the file, not on the text,
  # because the report prints the extracted ref and never the source line.
  [ "$(printf '%s\n' "$out" | grep -c 'sub.yml')" = 0 ] \
    || { echo "  self-test: false positive in a file with no steps or containers" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'tmpl/act@v1')" = 1 ] \
    || { echo "  self-test: .tmpl scaffold template not scanned" >&2; rc=1; }
  [ "$(printf '%s\n' "$out" | grep -c 'tmpl/img:latest')" = 1 ] \
    || { echo "  self-test: .tmpl container: not scanned" >&2; rc=1; }

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

  # --- the scan ROOT, which nothing above can see --------------------------
  # Everything so far calls scan() directly, so none of it exercises the root the
  # top level actually scans: revert `scan "."` to the two enumerated roots and
  # every assertion above stays green. That is exactly the half that hid 18
  # mutable refs in the scaffold templates of the sibling copy -- the coverage bug
  # invisible to the tests written to catch coverage bugs. It needs an end-to-end
  # case: re-run this script against a planted tree whose ONLY unpinned ref lives
  # outside .github, and require it to fail.
  #
  # `bash`, not `sh`: this script uses process substitution, so `sh` dies with a
  # syntax error -- and a crash must never be readable as "the ref was found".
  # For the same reason the exit code is compared to 1 exactly rather than tested
  # with `if`: exit 2 is a usage/environment error, not a finding.
  #
  # Two trees, not one. This copy has two detectors, `uses:` and container/image,
  # and a single tree containing both kinds of violation would still exit 1 if
  # only one of them ever reached outside .github.
  mkdir -p "$tmp/tree/.github/workflows" "$tmp/tree/templates"
  cat > "$tmp/tree/.github/workflows/ci.yml" <<'YML'
jobs:
  a:
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
YML
  cat > "$tmp/tree/templates/scaffold.yml.tmpl" <<'TMPL'
jobs:
  a:
    steps:
      - uses: outside/dot-github@v1
TMPL
  bash "$SELF" "$tmp/tree" >/dev/null 2>&1; planted_rc=$?
  [ "$planted_rc" -eq 1 ] \
    || { echo "  self-test: top-level scan root misses uses: outside .github (exit $planted_rc)" >&2; rc=1; }

  # The same question for the container/image detector. `service-integration/` was
  # the second enumerated root, so an image two directories from either one is the
  # case that a "just add the missing root" fix would still not cover.
  mkdir -p "$tmp/img/.github/workflows" "$tmp/img/deploy"
  cat > "$tmp/img/.github/workflows/ci.yml" <<'YML'
jobs:
  a:
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
YML
  cat > "$tmp/img/deploy/job.yml" <<'YML'
jobs:
  a:
    container: outside/dot-github:latest
YML
  bash "$SELF" "$tmp/img" >/dev/null 2>&1; planted_rc=$?
  [ "$planted_rc" -eq 1 ] \
    || { echo "  self-test: top-level scan root misses container: outside .github (exit $planted_rc)" >&2; rc=1; }

  [ "$rc" -eq 0 ] && echo "  self-test passed (detector fires, and goes quiet when fixed)"
  return "$rc"
}

if [ "$SELF_TEST" -eq 1 ]; then
  self_test || exit 1
fi

cd "$ROOT" 2>/dev/null || { echo "check-action-pinning.sh: no such directory: $ROOT" >&2; exit 2; }

# The whole repository, not a list of places to look. The previous version named
# ".github/workflows" and "service-integration/.github/workflows" -- a list is only
# as complete as its author's memory, and in the sibling copy of this script that
# omission hid 18 mutable refs in a scaffold-templates directory two levels away.
# A checker whose verdict depends on where it happened to look reports "all refs
# are pinned" while the unpinned ones sit in a file it never opened. Scan
# everything; waive by comment.
findings="$(scan ".")"

if [ -n "$findings" ]; then
  echo "  mutable action refs — pin to a 40-char commit SHA with a '# <version>' comment:" >&2
  printf '%s\n' "$findings" | sed 's/^/    /' >&2
  echo "  resolve an action:    gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq .object.sha" >&2
  echo "  resolve a container: docker buildx imagetools inspect <image>:<tag> | head -2" >&2
  exit 1
fi

echo "  all action refs are SHA-pinned and all container images are digest-pinned"
