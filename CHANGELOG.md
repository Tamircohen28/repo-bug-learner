# Changelog

See [docs/CHANGELOG.md](docs/CHANGELOG.md) for full history.

## [Unreleased]

### Changed

- `docker-compose.yml`'s `pgvector/pgvector:pg17` now carries an explicit
  `action-pin-ok:` waiver. The whole-tree pinning scan reaches it, so it had to be
  settled rather than discovered in CI. It was settled on evidence: no workflow and
  no Makefile target starts this compose file — every reference is human instruction
  (`README.md`, `AGENTS.md`, `docs/user/*`, and a Prerequisites comment in
  `scripts/bootstrap.sh`), and no workflow declares `services:` or `container:` at
  all. It is a developer's local database that never holds a GitHub token, and a
  digest pin would freeze every developer's Postgres at one patch release for no
  security gain. Waived by comment, on the line, with the reason: a path-shaped
  carve-out is how the mutable ref creeps back into a job that *does* hold the token.

### Removed

- `.github/workflows/regression-tests.yml`. After it was changed to call `make test`,
  it ran a command byte-identical to `ci.yml`'s `test (3.12)` leg on an identical
  trigger, so it was a second thing to keep in sync rather than a second signal — the
  failure mode that let both the directory-target and pip-less-venv bugs be fixed in
  one place and not the other. `Scan emulator regression tests` was not a required
  status check in either active ruleset (only `CI` is), so no merge gate changed. The
  iter-17..iter-20 provenance from its header moved into the docstring of
  `scripts/test_scan_repo_paths.py`.

### Fixed

- `scripts/check-action-pinning.sh` decided its verdict by where it looked. Six
  defects, all of which let it print "all action refs are SHA-pinned" over a tree
  that had unpinned ones:
  - It scanned two enumerated roots, `.github/workflows` and
    `service-integration/.github/workflows`. A list of places to look is only as
    complete as the memory of whoever wrote it; in the sibling copy of this script
    that same omission hid 18 mutable refs in a scaffold-templates directory. It now
    walks the whole repository — every `*.yml`, `*.yaml`, `*.tmpl` and `*.md`, with
    `.git`, `node_modules` and `.venv` pruned. `.tmpl` because a scaffold template is
    a workflow before it is rendered.
  - `uses:` was matched as a substring anywhere on the line, so the sentence
    `**Common errors and their causes:**` parsed as a step named `ca-uses:` and was
    reported as an unpinned ref. `uses:`, `container:` and `image:` are now matched as
    YAML keys that begin the line, after an optional sequence dash — which also stops
    `runner-image:` from being read as `image:`.
  - Once `.md` came into scope, prose *about* a mutable ref read as a mutable ref: a
    changelog entry explaining that `uses: actions/checkout@v7` names a movable tag
    was itself reported. In Markdown only, fenced-code delimiters are now tracked and
    lines outside a fence are treated as prose. (This very entry is the fixture.)

  - `action-pin-ok:` was itself matched as a substring anywhere on the line, so an
    action or image whose *name* carries the token — `uses: owner/action-pin-ok@v1`,
    `container: owner/action-pin-ok:latest` — waived itself and was never reported.
    Only the text after the first `#` can waive now. The waiver was the one thing
    left that a hostile or merely unlucky name could turn off.

  - The self-test could not see the scan root at all. Every assertion called
    `scan()` directly, so reverting the top-level `scan "."` back to the two
    enumerated roots left the whole suite green — the coverage bug was invisible to
    the tests written to catch coverage bugs. There is now an end-to-end case that
    re-invokes the script against a planted tree whose only unpinned ref lives
    outside `.github` and requires exit 1 exactly. Two trees, because this copy has
    two detectors: one plants a `uses:` in `templates/`, the other a `container:` in
    `deploy/`, so neither is covered by accident. It runs under `bash`, not `sh` —
    the script uses process substitution, and a syntax-error exit must never read as
    a finding — and the exit code is compared to 1 rather than tested with `if`,
    because exit 2 is a usage error.

  - The `docker://` branch printed a finding *unconditionally*, before any digest
    handling, and every finding exits 1 — so
    `uses: docker://ghcr.io/owner/img@sha256:<64 hex>`, already immutably pinned,
    failed the check and was told to pin by digest. This header called `docker://`
    "reported, not failed" from #18 onward, which was never true of the code. A
    docker ref is now routed through a real digest test (`@sha256:` plus exactly 64
    lowercase hex), and the header records the rule instead of the wish. This was
    the second of three defects inside the exemption path, which is under-tested by
    nature: its job is to make findings disappear, so a bug there is silent. A gate
    whose own remedy does not clear it is what drives someone to add the
    path-shaped carve-out the header warns about two lines later.

  The self-test now carries a case for each: an unfenced `uses:` in prose that must
  not be reported, a fenced one that must be, a `causes:` inside a `run:` that must
  not be, a `.yml.tmpl` that must be, a ref whose own name contains
  `action-pin-ok` that must be, a planted tree that must fail from outside
  `.github`, a digest-pinned `docker://` ref that must NOT be reported, and a
  truncated `@sha256:abc123` that must be. Each fix was reverted in a scratch copy and
  the self-test confirmed to go red with a distinct message, because a self-test that
  still passes with the fix reverted is asserting nothing.
- The CI Python matrix now tests the versions it names. `make test` picks its
  interpreter by probing `PATH` for `python3.13`, `python3.12`, `python3.11` in that
  order, and `ubuntu-latest` ships `/usr/bin/python3.12` — so the `3.11` leg built a
  3.12 venv and reported green for a floor it never exercised. Both workflows now pass
  `PYTHON` explicitly and assert that the venv they built runs the version the job
  pins, rather than trusting the probe.
- `regression-tests.yml` no longer re-implements the test suite. It ran its own
  `python -m venv` + `pip install semgrep` + script invocations, so neither the
  directory-target fix nor the pip-less-venv fix reached it; its `3.12` pin was all
  that kept it green. It now calls `make test`, which is a strict superset of what it
  ran.

- The semgrep install no longer assumes the venv has pip. `uv sync` builds `.venv`
  without pip, so `make test` on a checkout that had run `make install` died on
  `make: .venv/bin/pip: No such file or directory`. It now prefers `uv pip install`,
  falls back to the venv's own pip, and bootstraps pip via `ensurepip` only as a last
  resort. CI never hit this because `actions/setup-python` + `python -m venv` does
  ship pip.
- CI `lint` job no longer installs ruff unpinned. Ruff 0.16 widened its default rule
  set, which turned every fresh CI run red on an unchanged repo and blocked Dependabot
  PRs. The rule set is now declared explicitly in `[tool.ruff.lint]`, the version is
  pinned in the `dev` extra, and CI runs the documented `make lint` target rather than
  a divergent inline command.
- The test venv is built on a Python that meets the declared floor. `pyproject`
  requires `>=3.11`, but `make test`/`make precision` ran `python -m venv .venv`
  against ambient `python` — 3.10.4 on a pyenv machine, below the floor, silently.
  The Makefile now selects the first interpreter that clears 3.11 (override with
  `make test PYTHON=...`) and fails with a clear message when there is none, instead
  of the old `2>/dev/null || true` that surfaced as `no such file: .venv/bin/python`.
  Readiness is tracked by a stamp file rather than the `.venv` directory itself,
  because `make install` (`uv sync`) creates that directory without semgrep and on
  an interpreter of its own choosing — a directory target reads as up to date in
  both cases, so `make install && make test` reached the precision check with no
  `.venv/bin/semgrep`, and an existing 3.10 venv slipped past the floor entirely.
- `actions/setup-python` v6 -> v7 in `regression-tests.yml`. The bump landed in
  `ci.yml` only, so the other workflow was left behind.

### Changed

- Platform targets refreshed: `claude_code` 2.0.0 -> 2.1.263 and `cursor` 0.45.0 ->
  3.19.13 (validated), `codex` `latest_known` 0.40.0 -> 0.153.4 with `validated_against`
  left as `"unknown"` because nothing here was actually run against it. README badges
  regenerated to match.
- Claude model references moved from `claude-opus-4-8` to `claude-opus-5`
  (`config/config.example.toml`, AGENTS.md, stage4 synthesis docstring).
- `make lint` runs the pinned ruff via `uvx`, so it needs no prior `make install`;
  added `make lint-fix`.
- Timezone-aware datetimes throughout (`datetime.now(UTC)` instead of naive `now()`
  and deprecated `utcnow()`); `fromisoformat` now parses trailing `Z` natively.
- Every `subprocess.run` call declares `check=` explicitly.
- `scripts/precision_check.py` writes to a real temp directory instead of a fixed
  `/tmp` path.
- Vendored contract check scripts refreshed from `tamirs-superpowers@3.6.1` (were
  1.6.1). The newer `check-platform-targets.sh` cross-checks the capability registry,
  so each entry in `platform-targets.json` now names the platform that owns it.
- CI runs the test job as a `3.11 / 3.12 / 3.13` matrix with `fail-fast: false`.
  Only 3.12 was ever exercised, so both ends of the supported range were untested.
  The legs roll up into the existing `CI` fan-in job, so the branch ruleset is
  unchanged.
- `ci.yml` and `regression-tests.yml` declare a `concurrency` group with
  `cancel-in-progress`, so a force-push stops racing its own superseded run for the
  required `CI` context. `release.yml` is deliberately excluded — cancelling a
  half-finished release is worse than a duplicate run.

### Added

- `uv.lock` is now tracked. Every runtime dependency in `pyproject.toml` is declared
  as a lower bound with no ceiling, so two `make install` runs on different days
  could resolve to different versions with nothing recording which one was tested.
  This repo has already paid for that once — an unpinned ruff turned a green CI red
  on an unchanged tree. Verified with `uv lock --check` (73 packages, consistent
  with pyproject) and a `uv sync --frozen` install that runs the suite green.
- `core/capabilities/platforms.json` + `schema.json` — the single source of truth for
  what each supported agent surface (Claude Code, Cursor, Codex) can actually do.
  Every supported surface answers all 19 capability keys, nothing is claimed `native`
  without a validation command, and unmeasured surfaces (Claude Desktop, Cursor CLI,
  Codex IDE) are recorded as `unverified` with no capability claims rather than
  invented ones.
- `make skill-bridge` / `make skill-bridge-check` — `.claude/skills` is now a
  generated mirror of the canonical `.agents/skills`, asserted by `make agent:check`.
  The two trees were hand-copied and could diverge with the whole gate still green.
- Multi-platform README badges, platform-targets docs, and agent polish gates
- Portable canonical skill payload at `.agents/skills/repo-bug-review/`
- Root CHANGELOG mirror and versioning policy doc

### Security

- `service-integration/.github/workflows/opengrep.yml` no longer declares
  `container: opengrep/opengrep:latest`. No such image exists on any registry —
  Docker Hub returns `404 {"message":"object not found"}`, GHCR returns `404`, and
  none of the upstream repo's workflows publish one — so the job could never have
  started. The template now runs on `ubuntu-latest` and installs the `v1.30.0`
  release binary, verified against a recorded SHA-256 before it is made executable,
  so a moved or replaced asset fails the checksum rather than executing beside a
  `security-events: write` token. The job then asserts that `opengrep --version`
  reports the version it pinned, because a version written into a workflow is a
  claim about what will run, not a test that it did.
- `scripts/check-action-pinning.sh` now reads `container:` and `services.*.image:`
  in addition to `uses:`, and requires an image digest (`name@sha256:<64 hex>`).
  Both keys pull a registry image that runs with the job's own permissions, and
  `uses:`-only scanning could not see either — the whole class was unchecked until
  it was looked for.

## [0.1.0] - 2026-06-01

- Initial repo-bug-learner release — Jira/GitHub mining, rule synthesis, validation pipeline
