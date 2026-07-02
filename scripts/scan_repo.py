#!/usr/bin/env python3
"""
Phase 7: in-depth repo scanner for the repo-bug-learner pipeline.

Scans a target Scala repo using synthesized scalafix rules + optional
agent-driven deep checks. Findings are emitted by severity with citations
back to the PRs that motivated each rule.

Default mode is the fast regex emulator. Pass --use-sbt for the real
`sbt scalafixAll --check` sweep (slow, requires the scalafix rule set
to be wired into the target repo).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Rule discovery + rationale parsing
# ---------------------------------------------------------------------------

_DEFAULT_GITHUB_ORG = "your-org"


def _pr_url_re(github_org: str) -> re.Pattern[str]:
    return re.compile(rf"https://github\.com/{re.escape(github_org)}/[\w\-]+/pull/(\d+)")
# iter-24: many rationales cite PRs as "PR #12345" or "PR-12345" or "#12345"
# without a full URL. Default repo hint comes from --github-org / --repo-hint.
PR_BARE_RE = re.compile(r"\bPR[ \-#]?(\d{3,6})\b")
HIGH_KW = ("security", "identity leak", "data loss", "auth", "credential", "escalat")
LOW_KW = ("stylistic", "lint-only", "cosmetic", "style nit")


@dataclass
class Citation:
    pr_url: str
    title: str = ""


@dataclass
class RuleSpec:
    name: str
    source_path: str
    rationale_path: str | None
    severity: str
    diagnostic_keywords: list[str]
    regex_hint: str | None
    citations: list[Citation] = field(default_factory=list)


@dataclass
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    snippet: str
    message: str
    citations: list[dict]


def _derive_severity(text: str) -> str:
    low = text.lower()
    if any(k in low for k in HIGH_KW):
        return "high"
    if any(k in low for k in LOW_KW):
        return "low"
    # explicit severity line?
    m = re.search(r"^\s*severity\s*[:=]\s*(high|medium|low)", text, re.I | re.M)
    if m:
        return m.group(1).lower()
    return "medium"


def _parse_citations(text: str, github_org: str = _DEFAULT_GITHUB_ORG, repo_hint: str = "backend") -> list[Citation]:
    seen: dict[str, Citation] = {}
    for m in _pr_url_re(github_org).finditer(text):
        url = m.group(0)
        if url in seen:
            continue
        # title = surrounding parenthetical if present
        tail = text[m.end():m.end() + 200]
        tm = re.match(r"\s*\(([^)]+)\)", tail)
        title = tm.group(1).strip() if tm else ""
        seen[url] = Citation(pr_url=url, title=title)
    # iter-24: also pick up bare "PR #12345" / "PR-12345" / "#12345" forms.
    for m in PR_BARE_RE.finditer(text):
        num = m.group(1)
        url = f"https://github.com/{github_org}/{repo_hint}/pull/{num}"
        if url in seen:
            continue
        tail = text[m.end():m.end() + 200]
        # Title heuristic: rest-of-line or "(...)" parenthetical
        tm = re.match(r"\s*[—\-:]\s*([^\n]{1,160})", tail)
        title = tm.group(1).strip() if tm else ""
        seen[url] = Citation(pr_url=url, title=title)
    return list(seen.values())


def _find_rationale_for_rule(rule_name: str, search_dirs: list[Path]) -> Path | None:
    for base in search_dirs:
        if not base.exists():
            continue
        for r in base.rglob("rationale.md"):
            try:
                txt = r.read_text(errors="replace")
            except OSError:
                continue
            if rule_name in txt:
                return r
    # second pass: cluster_005 explicitly maps to MissingWithAdapterIdentity
    if rule_name == "MissingWithAdapterIdentity":
        for base in search_dirs:
            cand = base / "cluster_005" / "rationale.md"
            if cand.exists():
                return cand
    return None


def discover_rules(rules_dir: Path, rationale_roots: list[Path], github_org: str = _DEFAULT_GITHUB_ORG, repo_hint: str = "backend") -> list[RuleSpec]:
    """Scan rules_dir for scalafix Rule sources, build a RuleSpec per rule."""
    if not rules_dir.exists():
        raise SystemExit(f"rules-dir does not exist: {rules_dir}")

    rule_sources: list[Path] = []
    # Prefer the canonical scalafix layout
    src_main = rules_dir / "src" / "main" / "scala"
    if src_main.exists():
        rule_sources.extend(src_main.rglob("*.scala"))
    # Also pick up sibling Rule.scala files (candidates_v2/cluster_XXX style)
    rule_sources.extend(rules_dir.rglob("Rule.scala"))

    specs: list[RuleSpec] = []
    seen_names: set[str] = set()
    for src in rule_sources:
        try:
            txt = src.read_text(errors="replace")
        except OSError:
            continue
        # Find the rule class declaration. Match `class Foo extends SyntacticRule("Foo")`
        m = re.search(
            r"class\s+(\w+)\s+extends\s+(?:Syntactic|Semantic)Rule\(\s*\"([^\"]+)\"",
            txt,
        )
        if m:
            name = m.group(2)
        else:
            # Fall back to the class name itself
            m2 = re.search(r"class\s+(\w+)\s+extends\s+(?:Syntactic|Semantic)Rule", txt)
            if not m2:
                continue
            name = m2.group(1)
        if name in seen_names:
            continue
        seen_names.add(name)

        rationale_path = _find_rationale_for_rule(name, rationale_roots)
        rationale_txt = ""
        if rationale_path:
            try:
                rationale_txt = rationale_path.read_text(errors="replace")
            except OSError:
                pass

        severity = _derive_severity(rationale_txt) if rationale_txt else "medium"
        citations = _parse_citations(rationale_txt, github_org=github_org, repo_hint=repo_hint) if rationale_txt else []

        # Diagnostic message keywords (used by the fallback regex emulator)
        diag_keywords: list[str] = []
        for dm in re.finditer(r'message\s*=\s*\n?\s*s?"([^"]+)"', txt):
            diag_keywords.append(dm.group(1))
        # Regex hint declared explicitly in the rationale?
        regex_hint = None
        for rm in re.finditer(r"^#?\s*Regex hint\s*[:=]\s*(.+)$", rationale_txt, re.I | re.M):
            regex_hint = rm.group(1).strip()
            break

        specs.append(
            RuleSpec(
                name=name,
                source_path=str(src),
                rationale_path=str(rationale_path) if rationale_path else None,
                severity=severity,
                diagnostic_keywords=diag_keywords,
                regex_hint=regex_hint,
                citations=citations,
            )
        )

    # Also add Python emulator rules that don't have scalafix Rule.scala sources.
    # These are defined in SPECIALIZED_EMULATORS and need RuleSpecs for discovery.
    for rule_name in SPECIALIZED_EMULATORS.keys():
        if rule_name in seen_names:
            continue  # Skip if already discovered from scalafix
        seen_names.add(rule_name)

        rationale_path = _find_rationale_for_rule(rule_name, rationale_roots)
        rationale_txt = ""
        if rationale_path:
            try:
                rationale_txt = rationale_path.read_text(errors="replace")
            except OSError:
                pass

        severity = _derive_severity(rationale_txt) if rationale_txt else "medium"
        citations = _parse_citations(rationale_txt, github_org=github_org, repo_hint=repo_hint) if rationale_txt else []

        specs.append(
            RuleSpec(
                name=rule_name,
                source_path="",  # No source file; it's a Python emulator
                rationale_path=str(rationale_path) if rationale_path else None,
                severity=severity,
                diagnostic_keywords=[],
                regex_hint=None,
                citations=citations,
            )
        )

    return specs


# ---------------------------------------------------------------------------
# File enumeration
# ---------------------------------------------------------------------------

# iter-25: extended to catch `*-test-kit/src/main/` convention. These
# directories live on the main source root (not under /test/) but exist to
# support tests in OTHER modules — should not be production-flagged.
TEST_PATH_RE = re.compile(
    r"(?:^|/)(?:test|tests|it)/"
    r"|Test\.scala$|IT\.scala$|Spec\.scala$"
    r"|-test-kit/|/test-kit/|/testkit/|TestKit\.scala$|TestKit/"
)
# iter-19: exclude tooling-created worktree paths (e.g. Claude Code's per-branch
# checkouts under .claude/worktrees/<branch>/...). These contain duplicate copies
# of repo files and inflate every scan's finding count.
TOOLING_PATH_RE = re.compile(r"(?:^|/)\.(?:claude|git)/|/worktrees?/|/bazel-(?:bin|out|testlogs)/|/target/|/node_modules/|/build/")


def enumerate_files(
    repo: Path,
    patterns: list[str],
    include_tests: bool = False,
    excludes: list[str] | None = None,
) -> list[Path]:
    if not patterns:
        patterns = ["**/*.scala"]
    excludes = excludes or []
    out: set[Path] = set()
    for pat in patterns:
        # glob is anchored at repo
        for p in repo.glob(pat):
            if p.is_file():
                out.add(p)
        # Allow **/*.scala style even when glob returns nothing (e.g. when the
        # leading directory does not exist on this machine but a user expected
        # repo-wide search).
    if not out:
        for p in repo.rglob("*.scala"):
            # respect the patterns by fnmatch
            rel = str(p.relative_to(repo))
            if any(fnmatch.fnmatch(rel, pat) for pat in patterns):
                out.add(p)
    if not include_tests:
        out = {p for p in out if not TEST_PATH_RE.search(str(p.relative_to(repo)))}
    # iter-19: always exclude tooling/cache paths
    out = {p for p in out if not TOOLING_PATH_RE.search(str(p.relative_to(repo)))}
    if excludes:
        out = {
            p for p in out
            if not any(
                fnmatch.fnmatch(str(p.relative_to(repo)), pat) for pat in excludes
            )
        }
    return sorted(out)


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------

ADAPTER_CLASS_RE = re.compile(r"^\s*(?:final\s+|abstract\s+|sealed\s+)*class\s+(\w*Adapter)\b", re.M)
DEF_RE = re.compile(r"^[ \t]*(?:override\s+|private\s+|protected\s+|final\s+)*def\s+(\w+)\s*[\[\(]", re.M)


# iter-2: types that indicate a direct downstream-service call. If the method body
# doesn't reference at least one field of such a type, the adapter is a wrapper that
# delegates to private helpers — those helpers do the signing.
DOWNSTREAM_TYPE_SUFFIXES = (
    "PlatformizedClientMethods", "ClientMethods", "PlatformizedClient",
    "ServicePlatformizedClient", "GrpcClient", "RpcClient", "Rpc",
)
# Match: `foo: TypeSuffix` in ctor or `val foo: TypeSuffix` or `private val foo: TypeSuffix`
FIELD_TYPE_RE = re.compile(
    r"\b(?:val|var)?\s*([a-zA-Z_]\w*)\s*:\s*([a-zA-Z_][\w.]*?)"
    r"(?=\s*[,)=\n])"
)


def _downstream_fields(class_header: str, class_body: str) -> set[str]:
    """Return field names whose declared type ends in a downstream-service suffix."""
    fields: set[str] = set()
    # Constructor params live in the class header (between class Foo(...) and the body)
    for src in (class_header, class_body):
        for m in FIELD_TYPE_RE.finditer(src):
            name, tname = m.group(1), m.group(2)
            tail = tname.split(".")[-1]
            if any(tail.endswith(s) for s in DOWNSTREAM_TYPE_SUFFIXES):
                fields.add(name)
    return fields


def scan_missing_with_adapter_identity(path: Path, text: str) -> list[tuple[int, str, str]]:
    """Heuristic emulator for the MissingWithAdapterIdentity rule.

    Returns a list of (line, snippet, message).
    """
    hits: list[tuple[int, str, str]] = []
    classes = list(ADAPTER_CLASS_RE.finditer(text))
    if not classes:
        return hits

    # Find the body of each Adapter class by brace-matching.
    for cm in classes:
        cls_name = cm.group(1)
        # Find '{' after the class header
        brace_open = text.find("{", cm.end())
        if brace_open < 0:
            continue
        depth = 0
        i = brace_open
        end = len(text)
        while i < end:
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
            i += 1
        body = text[brace_open:end]
        body_offset = brace_open
        class_header = text[cm.start():brace_open]
        ds_fields = _downstream_fields(class_header, body)
        if not ds_fields:
            # No downstream-client field declared. Adapter is a thin wrapper / DTO.
            # iter-2 fix: skip — wrappers delegate to helpers that do the signing.
            continue
        # Pre-compile field-call regex once per class
        field_alt = "|".join(re.escape(f) for f in ds_fields)
        FIELD_CALL_RE = re.compile(rf"\b(?:{field_alt})\s*\.\s*\w+\s*\(")

        # Walk each def inside the class body
        for dm in DEF_RE.finditer(body):
            def_name = dm.group(1)
            def_start = dm.start()
            # Determine method body by locating the '=' or '{' and brace-matching
            # We grab a generous window after the def header to inspect.
            window_end = min(len(body), def_start + 4000)
            window = body[def_start:window_end]
            # Heuristic: needs implicit CallScope in signature
            sig_end = window.find("=")
            if sig_end < 0:
                continue
            signature = window[:sig_end]
            if "implicit" not in signature or "CallScope" not in signature:
                continue
            method_block = window[sig_end:]
            # Trim to next sibling def to avoid bleeding into the next method
            next_def = re.search(r"\n[ \t]*(?:override\s+|private\s+|protected\s+|final\s+)*def\s+\w+", method_block[1:])
            if next_def:
                method_block = method_block[: 1 + next_def.start()]
            # Only `visibility.exposing` is the service-call wrapper; `visibility.expose(...)`
            # is fire-and-forget logging and does not call out. (iter-1 fix)
            if not re.search(r"visibility\s*\.\s*exposing\b", method_block):
                continue
            # Any of these means the adapter signs identity correctly. (iter-1 fix)
            if re.search(
                r"\b(?:withAdapterIdentity|withServiceIdentity|addServiceIdentity|signWithAdapterIdentity)\b",
                method_block,
            ):
                continue
            # iter-2 fix: method must DIRECTLY call a downstream-client field.
            # Otherwise it's a wrapper delegating to a private helper that does the signing.
            if not FIELD_CALL_RE.search(method_block):
                continue
            abs_off = body_offset + def_start
            line = text.count("\n", 0, abs_off) + 1
            snippet = text[abs_off : abs_off + 200].replace("\n", " ").strip()
            msg = (
                f"Adapter method `{def_name}` in class `{cls_name}` takes an implicit "
                f"CallScope and calls visibility.exposing(...) without wrapping in "
                f"`serverSigner.withAdapterIdentity {{ ... }}`. Risks leaking the caller's "
                f"service identity to downstream services."
            )
            hits.append((line, snippet, msg))
    return hits


# Map of rule names -> specialized emulator. Anything not in here falls back
# to the keyword/regex-hint emulator.
# --- StatusRuntimeExceptionForBusinessError ---------------------------
# Look for: a class that `extends StatusRuntimeException(... responseStatus = ResponseStatus.<X> ...)`
# where X is one of the non-Internal business statuses. Skip when X is Internal.
WSRE_CLASS_RE = re.compile(
    r"class\s+(\w+)[^{}]{0,400}?extends\s+StatusRuntimeException\s*\(([^)]{0,2000}?)\)",
    re.DOTALL,
)
BUSINESS_STATUSES = (
    "InvalidArgument", "FailedPrecondition", "NotFound", "AlreadyExists",
    "PermissionDenied", "Unauthenticated", "ResourceExhausted",
    "OutOfRange", "Aborted", "Unavailable", "DeadlineExceeded",
    "Unimplemented", "Cancelled",
)
WSRE_STATUS_RE = re.compile(
    r"responseStatus\s*=\s*ResponseStatus\.(" + "|".join(BUSINESS_STATUSES) + r")\b"
)


# iter-2: skip when responseStatus is `Internal` ANYWHERE in the class definition or its
# companion object, and skip when class name ends in `SystemException` (system-error convention).
WSRE_INTERNAL_RE = re.compile(r"ResponseStatus\.Internal\b")
WSRE_PARAM_STATUS_RE = re.compile(
    r"\b(?:override\s+(?:val|var)\s+)?responseStatus\s*:\s*ResponseStatus\b"
)


def scan_status_runtime_business_error(path: Path, text: str) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    for m in WSRE_CLASS_RE.finditer(text):
        cls_name = m.group(1)
        ctor_args = m.group(2)
        # iter-2: convention — `*SystemException` is genuinely an internal/system error.
        if cls_name.endswith("SystemException"):
            continue
        # iter-2: get a generous slice of the class + companion object to look for
        # an `Internal` literal anywhere associated with this class.
        class_start = m.start()
        class_end = min(len(text), m.end() + 4000)
        scope = text[class_start:class_end]
        if WSRE_INTERNAL_RE.search(scope):
            continue
        # iter-2/3: if responseStatus is declared as a class parameter (with or
        # without override val), the caller decides — without call-site analysis
        # we cannot judge. Search the WHOLE scope (class header + body), not just
        # the StatusRuntimeException super-call args.
        if WSRE_PARAM_STATUS_RE.search(scope):
            continue
        status = WSRE_STATUS_RE.search(ctor_args)
        if not status:
            status = WSRE_STATUS_RE.search(scope)
            if not status:
                continue
        biz = status.group(1)
        abs_off = m.start()
        line = text.count("\n", 0, abs_off) + 1
        snippet = text[abs_off : abs_off + 200].replace("\n", " ").strip()
        msg = (
            f"Class `{cls_name}` extends StatusRuntimeException with non-Internal "
            f"responseStatus `{biz}`. Business errors should extend "
            f"a domain-specific ApplicationException with an applicationDetails code instead."
        )
        hits.append((line, snippet, msg))
    return hits


# --- UnclampedOpenSpots --------------------------------------------------
# Look for: a subtraction whose result is assigned to / passed as an open-spots-like
# value, with capacity-like LHS and participants-like RHS, not wrapped in Math.max(_, 0).
# iter-39: expanded pattern names to catch more variations
OPENSPOTS_NAMES = r"(?:openSpots|spotsOpen|spotsLeft|availableSpots|remainingCapacity|remainingSlots|availableSlots|freeSlots|slotCount)"
CAP_NAMES = r"(?:capacity|maxParticipants|totalCapacity|maxCapacity|maxSlots|slotCapacity|totalSlots|maxAttendees)"
PART_NAMES = r"(?:numberOfParticipants|participantsCount|participants|registeredCount|enrolledCount|attendeeCount|participantCount|attendees|booked|reserved)"

# Pattern A: `val|var openSpots = capacity - participants`
PATTERN_A = re.compile(
    rf"\b(?:val|var)\s+{OPENSPOTS_NAMES}\s*(?::[^=]{{1,80}})?=\s*([^\n]{{0,200}})"
)
# iter-27: function-return form (`def spotsOpen = capacity - participants`).
# SCHED-21976's pre-patch site was `def spotsOpen = slot.capacity.get -
# slot.totalNumberOfParticipants` — a method, not a val. Adding this shape.
PATTERN_A2 = re.compile(
    rf"\b(?:def|lazy\s+val)\s+{OPENSPOTS_NAMES}\s*(?:\([^)]*\))?"
    rf"\s*(?::[^=]{{1,80}})?\s*=\s*([^\n]{{0,200}})"
)
# Pattern B: `.withOpenSpots(capacity - participants)` (or sibling setter names)
PATTERN_B = re.compile(
    r"\.\s*with(?:OpenSpots|SpotsOpen|SpotsLeft|AvailableSpots|RemainingCapacity)\s*\(\s*([^)]{0,200})\s*\)"
)
# iter-40: Also match generic subtraction, not just named patterns
SUBTRACT_RE = re.compile(
    rf"(?:\b{CAP_NAMES}(?:\.\w+)?\s*-\s*{PART_NAMES}\b"  # Named patterns
    r"|\b\w+\s*-\s*\w+\b)"  # Also generic subtraction
    , re.IGNORECASE
)
# iter-29: also recognize Scala-idiomatic clamping `Seq(x, 0).max`,
# `List(x, 0).max`, `Vector(x, 0).max` — alternatives to `Math.max(x, 0)`.
# iter-39: recognize more clamping patterns
MATH_MAX_RE = re.compile(
    r"\b(?:Math|math)\s*\.\s*max\s*\("
    r"|\b(?:Seq|List|Vector|Iterable|Array)\s*\([^)]*?,\s*0\s*\)\s*\.\s*max\b"
    r"|\b\.max\s*\(\s*0\s*\)"  # .max(0) pattern
    r"|(?:if|if\s*\()\s*\(\s*\w+\s*[<>]=?\s*0\s*\)"  # if (x < 0) pattern
)


def scan_unclamped_open_spots(path: Path, text: str) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    for pat, kind in (
        (PATTERN_A, "assignment"),
        (PATTERN_A2, "method return"),
        (PATTERN_B, "withOpenSpots call"),
    ):
        for m in pat.finditer(text):
            rhs = m.group(1)
            if not SUBTRACT_RE.search(rhs):
                continue
            if MATH_MAX_RE.search(rhs):
                continue
            abs_off = m.start()
            line = text.count("\n", 0, abs_off) + 1
            snippet = text[abs_off : abs_off + 200].replace("\n", " ").strip()
            msg = (
                f"Open-spots {kind} computes `capacity - participants` without "
                f"clamping with `Math.max(..., 0)`. Can produce negative values when "
                f"sessions are oversold."
            )
            hits.append((line, snippet, msg))
    return hits


# --- MissingDollarInInterpolation ---------------------------------------
# Targeted at the PR-16023 anti-pattern: s"foo = identifier" where the
# right side of an `=` inside an s-string is a bare camelCase identifier
# (no $ prefix) that also appears as a binding in the surrounding file.
# Lint-only / low severity — generous heuristic.
S_STRING_RE = re.compile(r'(?<![\w$])s"([^"\n]{1,400})"')
# Match a single `=` (not `==`, not `!=`, not `<=`, not `>=`) followed by a bare
# camelCase identifier. The negative lookbehind avoids matching the second `=` of
# `==` or comparison operators that frequently appear inside ${...} blocks.
BARE_RHS_RE = re.compile(r"(?<![=<>!])=\s*([a-z][A-Za-z0-9_]*)\b(?!\s*['\$=])")
BINDING_RE = re.compile(r"\b(?:val|var|def|lazy\s+val)\s+([a-z][A-Za-z0-9_]*)\b")


def scan_missing_dollar_interpolation(path: Path, text: str) -> list[tuple[int, str, str]]:
    """iter-40: Two-tier validation:
    - Tier 1 (conservative): Fire when bare ident is interpolated ELSEWHERE in file
    - Tier 2 (obvious cases): Fire on common variable names (userName, status, etc.)
      since bare `= variableName` is almost certainly a bug, not a literal label.
    """
    hits: list[tuple[int, str, str]] = []
    bindings = set(BINDING_RE.findall(text))
    if not bindings:
        return hits

    # Find all idents that ARE interpolated somewhere: `$ident` or `${ident...}`
    interpolated = set(re.findall(r"\$\{?([a-z][A-Za-z0-9_]*)", text))

    # Obvious common variable names (Tier 2)
    common_names = {
        'name', 'userName', 'email', 'id', 'count', 'total', 'status',
        'message', 'error', 'value', 'result', 'text', 'title', 'label',
        'firstName', 'lastName', 'phone', 'address', 'code', 'key', 'reason',
    }

    for m in S_STRING_RE.finditer(text):
        body = m.group(1)
        for rm in BARE_RHS_RE.finditer(body):
            ident = rm.group(1)
            if len(ident) < 4:
                continue
            if ident not in bindings:
                continue

            # Tier 1: Fire if interpolated elsewhere in file (conservative)
            tier1_match = ident in interpolated

            # Tier 2: Fire if it's a common variable name (obvious case)
            tier2_match = ident in common_names

            if not (tier1_match or tier2_match):
                # Neither tier matched
                continue

            # Don't fire if THIS s-string already interpolates the same ident
            if re.search(rf"\${{?{re.escape(ident)}\b", body):
                continue
            abs_off = m.start()
            line = text.count("\n", 0, abs_off) + 1
            snippet = text[abs_off : abs_off + 200].replace("\n", " ").strip()
            msg = (
                f"s-string contains bare identifier `{ident}` after `=` that is "
                f"interpolated as `${ident}` elsewhere in the file — likely a missing "
                f"`$` interpolation prefix."
            )
            hits.append((line, snippet, msg))
    return hits


# --- BrokenInterpolationFieldAccess -------------------------------------
# Pattern: s"..." or f"..." containing `$<ident>.<ident>` — an unbraced splice
# immediately followed by a `.fieldName` that renders literally rather than as
# member access. Skip braced `${...}` splices (correct) and skip when the
# `.` is not followed by an identifier character (sentence punctuation, etc.).
# Example bug: `s"submitted form $submission.id failed"` — `.id` renders literal.
BROKEN_INTERP_STRING_RE = re.compile(r'(?<![\w$])[sf]"((?:[^"\\\n]|\\.){1,500})"')
BROKEN_INTERP_SPLICE_RE = re.compile(
    r"(?<!\$)\$([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)"
)


# iter-4 tightening: only fire inside log/exception-message context. Path-building,
# metric name builders, file-extension concatenation are the dominant FP class —
# all of those live OUTSIDE log/exception calls. Use a per-line context check.
BROKEN_INTERP_CONTEXT_RE = re.compile(
    r"\b(?:logger|log|logInfo|logError|logWarn|logDebug|logTrace|"
    r"Exception|RuntimeException|throw\s+new|require\s*\(|assert\s*\(|"
    r"\.error\s*\(|\.warn\s*\(|\.info\s*\(|\.debug\s*\(|\.trace\s*\(|"
    r"message\s*=)\b",
    re.I,
)


def scan_broken_interpolation_field_access(
    path: Path, text: str
) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    for sm in BROKEN_INTERP_STRING_RE.finditer(text):
        body = sm.group(1)
        body_start = sm.start(1)
        # iter-4 context guard: find the line range containing this s-string and
        # the preceding 2 lines (the calling method is usually one line above).
        line_start = text.rfind("\n", 0, sm.start()) + 1
        # Look back to grab the previous 2 lines of context (call site).
        ctx_start = line_start
        for _ in range(2):
            prev_nl = text.rfind("\n", 0, ctx_start - 1)
            if prev_nl < 0:
                ctx_start = 0
                break
            ctx_start = prev_nl + 1
        context = text[ctx_start : sm.end()]
        if not BROKEN_INTERP_CONTEXT_RE.search(context):
            # Not in a log/exception/throw context — skip path-building, etc.
            continue
        for im in BROKEN_INTERP_SPLICE_RE.finditer(body):
            ident = im.group(1)
            field = im.group(2)
            abs_off = body_start + im.start()
            line = text.count("\n", 0, abs_off) + 1
            snippet = text[sm.start() : sm.start() + 240].replace("\n", " ").strip()
            msg = (
                f"String interpolation `${ident}.{field}` is missing braces — the "
                f"`.{field}` part renders literally instead of as a member access. "
                f"Likely meant `${{{ident}.{field}}}`."
            )
            hits.append((line, snippet, msg))
    return hits


# iter-4 decision: BrokenInterpolationFieldAccess Scalafix rule passes its own
# testkit but the regex emulator can't distinguish `$str.suffix` (intentional
# concatenation — path, metric-name, log-key) from `$obj.field` (the real bug).
# Determining splice type requires semantic info. Disable in fast mode; the rule
# remains compiled and shippable for `--use-sbt` scans where Scalafix has types.
FAST_SCAN_DISABLED = {"BrokenInterpolationFieldAccess"}


def _noop_scanner(path: Path, text: str) -> list[tuple[int, str, str]]:
    return []


# iter-5: tighter emulator — only fire when the suffix is a member-accessor name
# that's almost never a literal file extension or metric suffix. PR-24533 was
# `.id`; common bug-prone accessors are short property names. Exclude known
# file-extension / domain-suffix words.
MEMBER_ACCESSOR_ALLOWLIST = {
    "id", "code", "name", "value", "size", "length", "isEmpty", "nonEmpty",
    "head", "tail", "get", "getOrElse", "toString", "hashCode",
    "messageId", "userId", "siteId", "bookingId", "scheduleId", "serviceId",
    "resourceId", "businessId", "metaSiteId", "instanceId", "formId",
    "appId", "tenantId", "orderId", "policyId", "submissionId", "version",
    "status", "type", "kind", "title", "message", "reason", "details",
    "count", "amount", "total", "remaining", "available", "capacity",
}


def scan_broken_interpolation_field_access_v2(
    path: Path, text: str
) -> list[tuple[int, str, str]]:
    """iter-5: only fire on member-accessor allow-list suffixes."""
    hits: list[tuple[int, str, str]] = []
    for sm in BROKEN_INTERP_STRING_RE.finditer(text):
        body = sm.group(1)
        body_start = sm.start(1)
        line_start = text.rfind("\n", 0, sm.start()) + 1
        ctx_start = line_start
        for _ in range(2):
            prev_nl = text.rfind("\n", 0, ctx_start - 1)
            if prev_nl < 0:
                ctx_start = 0
                break
            ctx_start = prev_nl + 1
        context = text[ctx_start : sm.end()]
        if not BROKEN_INTERP_CONTEXT_RE.search(context):
            continue
        for im in BROKEN_INTERP_SPLICE_RE.finditer(body):
            ident = im.group(1)
            field = im.group(2)
            if field not in MEMBER_ACCESSOR_ALLOWLIST:
                continue
            abs_off = body_start + im.start()
            line = text.count("\n", 0, abs_off) + 1
            snippet = text[sm.start() : sm.start() + 240].replace("\n", " ").strip()
            msg = (
                f"String interpolation `${ident}.{field}` is missing braces — the "
                f"`.{field}` part renders literally instead of as a member access. "
                f"Likely meant `${{{ident}.{field}}}`."
            )
            hits.append((line, snippet, msg))
    return hits


# ---------------------------------------------------------------------------
# YAML (Semgrep/Opengrep) rule discovery + execution
# ---------------------------------------------------------------------------

def discover_yaml_rules(rules_dir: Path) -> list[Path]:
    """Find all Semgrep/Opengrep YAML rule files under rules_dir.

    Prefers rules_dir/opengrep/ as the canonical location, but also picks up
    any *.yaml/*.yml siblings of Rule.yaml further down the tree.
    """
    if not rules_dir.exists():
        return []
    out: list[Path] = []
    seen: set[Path] = set()
    preferred = rules_dir / "opengrep"
    if preferred.exists():
        for p in sorted(preferred.rglob("*.yaml")):
            r = p.resolve()
            if r not in seen:
                seen.add(r)
                out.append(p)
        for p in sorted(preferred.rglob("*.yml")):
            r = p.resolve()
            if r not in seen:
                seen.add(r)
                out.append(p)
    # Also pick up YAML rules elsewhere under rules_dir
    for ext in ("*.yaml", "*.yml"):
        for p in sorted(rules_dir.rglob(ext)):
            r = p.resolve()
            if r in seen:
                continue
            # Skip the deferred/ directory — rules there are testkit-validated but
            # not suitable for fast-mode regex/emulator scanning.
            if "deferred" in p.parts:
                continue
            # Skip non-rule yamls (configs, etc.) — must contain `rules:` key
            try:
                head = p.read_text(errors="replace")[:4000]
            except OSError:
                continue
            if re.search(r"^\s*rules\s*:", head, re.M):
                seen.add(r)
                out.append(p)
    return out


def _yaml_rule_ids(yaml_path: Path) -> list[str]:
    """Extract semgrep rule ids declared in a YAML file (simple parse)."""
    try:
        txt = yaml_path.read_text(errors="replace")
    except OSError:
        return []
    return re.findall(r"^\s*-\s*id\s*:\s*([\w\-.]+)\s*$", txt, re.M)


def run_semgrep_yaml(
    yaml_rules: list[Path], repo: Path, paths: list[str], semgrep_bin: str,
) -> list[Finding]:
    """Run semgrep with each YAML rule file against the repo. Parse JSON output
    into Finding records.
    """
    findings: list[Finding] = []
    if not yaml_rules:
        return findings
    for yp in yaml_rules:
        cmd = [semgrep_bin, "--quiet", "--json", "--config", str(yp), str(repo)]
        # Path globs: semgrep uses --include
        for pat in paths:
            cmd.extend(["--include", pat])
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
            )
        except FileNotFoundError:
            print(f"[scan] semgrep binary not found at {semgrep_bin}", file=sys.stderr)
            return findings
        except subprocess.TimeoutExpired:
            print(f"[scan] semgrep timed out on {yp}", file=sys.stderr)
            continue
        if not proc.stdout:
            if proc.returncode != 0:
                tail = proc.stderr.splitlines()[-5:]
                print(f"[scan] semgrep failed for {yp}: {' / '.join(tail)}",
                      file=sys.stderr)
            continue
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print(f"[scan] semgrep produced non-JSON output for {yp}",
                  file=sys.stderr)
            continue
        for r in data.get("results", []):
            fpath = r.get("path", "")
            try:
                rel = str(Path(fpath).resolve().relative_to(repo.resolve()))
            except (ValueError, OSError):
                rel = fpath
            line = (r.get("start") or {}).get("line", 0)
            check_id = r.get("check_id", "") or ""
            # Strip leading file-path prefix that semgrep prepends
            short_rule = check_id.rsplit(".", 1)[-1] if "." in check_id else check_id
            extra = r.get("extra") or {}
            msg = extra.get("message", "") or ""
            sev = (extra.get("severity") or "WARNING").lower()
            sev_map = {"error": "high", "warning": "medium", "info": "low"}
            severity = sev_map.get(sev, "medium")
            lines = (extra.get("lines") or "").strip()[:200]

            # iter-45: Skip test files to reduce false positive contamination
            if '/test/' in rel or '/it/' in rel or rel.endswith('Test.scala'):
                continue

            findings.append(
                Finding(
                    rule=short_rule,
                    severity=severity,
                    file=rel,
                    line=int(line) if line else 0,
                    snippet=lines,
                    message=msg.strip(),
                    citations=[],
                )
            )
    return findings


# --- StaffQueryMissingAppDefId ------------------------------------------
# Look for: `<staffOrMemberReceiver>.<method>(args...)` where none of `args`
# mentions appDefId/applicationDefinitionId/appId, either as a named arg or
# a positional reference to such a name.
# iter-20: removed `staffMembersAdapter` from this list. Adapters are the scoping
# boundary — they use `serverSigner.withAdapterIdentity` which encodes app-def-id
# via the signed CallScope. Calls to `staffMembersAdapter.X()` from callers are
# scoped automatically. Only the raw platformized SERVICE
# clients (and direct repository receivers) genuinely need explicit appDefId.
# iter-39: expanded staff receiver names
STAFF_RECV_RE = re.compile(
    r"\b(staffRepository|staffMembersService|membersRepository|staffApi|staffQueryService|memberService|staffService)"
    r"(?:\s*\.\s*)(\w+)\s*(?:\[[^\]]*\])?\s*\(",
    re.IGNORECASE,
)
APP_DEF_ID_RE = re.compile(
    r"(?i)\b(?:appDefId|applicationDefinitionId|appId)\b"
)
# Tightening — only flag enumerating verbs ending in `StaffMembers` (plural).
# Singletons (`fetchOrCreateDefaultStaffMember`) and mutators
# (`delete*`, `assign*`, etc.) are excluded entirely.
STAFF_ENUMERATING_METHOD_RE = re.compile(
    r"^(query|list|search|getAll|findAll|fetchAll)[A-Za-z]*[Ss]taff[Mm]embers$"
)
STAFF_NON_QUERY_VERB_RE = re.compile(
    r"^(delete|update|insert|assign|disconnect|connect|create|dispatch|notify"
    r"|fetchOrCreate|fetch[A-Z]|set[A-Z]|add[A-Z]|handle).*"
)


def scan_staff_query_missing_appdefid(
    path: Path, text: str
) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    for m in STAFF_RECV_RE.finditer(text):
        recv = m.group(1)
        method = m.group(2)
        # Tightening: restrict to enumerating verbs ending in `StaffMembers`.
        if STAFF_NON_QUERY_VERB_RE.match(method):
            continue
        if not STAFF_ENUMERATING_METHOD_RE.match(method):
            continue
        # Walk forward, brace-matching `(` to find the call's argument list.
        i = m.end() - 1  # position of `(`
        depth = 0
        end = -1
        n = len(text)
        while i < n:
            c = text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
            i += 1
        if end < 0:
            continue
        args = text[m.end():end]
        if APP_DEF_ID_RE.search(args):
            continue
        # Tightening 1: skip when the call passes a `*Request` proto (it
        # almost always carries the scoping fields internally). Also skip
        # when the only arg is a single bare `request`/`req` identifier.
        args_stripped = args.strip()
        if re.match(r"^(request|req)\s*$", args_stripped):
            continue
        # `someRequest` / `myRequest` / `QueryFooRequest(...)` — proto in scope.
        if re.search(r"\b\w*Request\b", args_stripped):
            continue
        # Tightening 2: skip when the receiver chain shows we're already inside
        # an Adapter file that wraps the service (the wrapper itself is the
        # scoping boundary). File path heuristic.
        path_str = str(path)
        if "/adapters/" in path_str.lower() and path_str.endswith("Adapter.scala"):
            continue
        # Tightening 3: skip lookup-by-ID style calls where the ID is globally
        # unique (resourceId, scheduleId) — these don't need app-def-id scoping.
        if re.search(
            r"(?:^|\b)(?:get|find|fetch|load)\w*By(?:Resource|Schedule|Booking|Member|Staff|User)Ids?\b",
            method,
        ):
            continue
        abs_off = m.start()
        line = text.count("\n", 0, abs_off) + 1
        snippet = text[abs_off:abs_off + 200].replace("\n", " ").strip()
        msg = (
            f"Call `{recv}.{method}(...)` is missing an `appDefId` "
            f"(or `applicationDefinitionId`/`appId`) argument. Unscoped "
            f"staff/member queries have caused cross-tenant leaks and "
            f"stale-cache bugs across configured repos."
        )
        hits.append((line, snippet, msg))
    return hits


# --- CalendarNowWithoutExplicitTimezone -----------------------------------
# Flags `<DateType>.now()` calls (no args) in files whose path or class name
# is calendar/availability/time-slot/schedule/booking related.
CAL_CONTEXT_RE = re.compile(
    r"(?i)(calendar|availability|timeslot|time_slot|schedule|booking)"
)
# Instant intentionally excluded — Instant.now() is always UTC by definition
# (verified against 9 FPs in the scheduler scan).
DATE_TYPES_RE = re.compile(
    r"\b(DateTime|LocalDateTime|LocalDate|OffsetDateTime|ZonedDateTime)"
    r"\.now\s*\(\s*\)"
)
# Epoch / UTC-canonical accessors that follow `<Type>.now()` and prove
# the value is timezone-agnostic.
EPOCH_ACCESSOR_RE = re.compile(
    r"\.\s*(getMillis|getEpochSecond|toEpochMilli|toEpochSecond|toInstant)\b"
)
TEST_FILE_RE = re.compile(
    r"(?:^|/)(test|tests|it)/|/TestClock\.scala$|Spec\.scala$|Test\.scala$"
    r"|/contract/|/contract-test/|/test-kit/|/testkit/|TestKit\.scala$"
    r"|TestUtils|TestWrapper|/__tests__/|/__mocks__/"
)
# Tightening — skip diagnostic / introspection contexts by class name.
DIAGNOSTIC_CLASS_RE = re.compile(
    r"\b(?:class|object|trait)\s+\w*"
    # iter-19: also skip Clock / TestClock — these are time-provider abstractions,
    # not bugs (the whole point of a Clock is encapsulating now()).
    r"(AppInfo|ServerDynamicConfig|HealthCheck|Diagnostic|TestClock|SystemClock|Clock)\w*"
)
# Tightening — skip when `.now()` is the value of a storage-timestamp named
# argument (heuristic: previous tokens look like `<name> = `, optionally
# wrapped in `Some(`/`Option(`), OR a case-class default arg of the same
# storage-timestamp name, e.g. `created: DateTime = DateTime.now()`.
STORAGE_TS_NAMED_ARG_RE = re.compile(
    r"\b(created|createdAt|updatedAt|updated|updateDate|updateTime|timeStamp|timestamp|dateUpdated"
    r"|dateCreated|lastModified|lastDbAccessTime|approvalTime|creationTime"
    r"|transactionTime|registeredAt|completedAt|modifiedAt|insertedAt"
    # iter-19 additions
    r"|reportedAt|loggedAt|emittedAt|firedAt|sentAt|receivedAt|publishedAt|recordedAt"
    r"|eventTime|logTime|reportTime)"
    r"(?:\s*:\s*[A-Za-z_][\w.]*\s*)?"
    r"\s*=\s*(?:Some\(\s*|Option\(\s*)?$"
)
# iter-19: skip when `.now()` is the fallback in `.getOrElse(...)` — Scala
# equivalent of TS's `?? new Date()` pattern. The caller-supplied date is the
# real intent; the fallback is just a safe default.
GETORELSE_FALLBACK_RE = re.compile(r"\.getOrElse\s*\(\s*$")


def scan_calendar_now_no_tz(
    path: Path, text: str
) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    path_str = str(path)
    path_ok = bool(CAL_CONTEXT_RE.search(path_str))
    # cheap class-name scan (only consult if path doesn't already trigger)
    class_ok = False
    if not path_ok:
        for cm in re.finditer(
            r"\b(?:class|object|trait)\s+(\w+)", text
        ):
            if CAL_CONTEXT_RE.search(cm.group(1)):
                class_ok = True
                break
    if not (path_ok or class_ok):
        return hits
    # Skip test/fixture files entirely.
    if TEST_FILE_RE.search(path_str):
        return hits
    # Skip diagnostic / introspection files (AppInfoController,
    # ServerDynamicConfig, HealthCheck, Diagnostic).
    if DIAGNOSTIC_CLASS_RE.search(text):
        return hits
    for m in DATE_TYPES_RE.finditer(text):
        abs_off = m.start()
        # Look ahead a few chars: if the very next non-whitespace is `.getMillis`
        # / `.getEpochSecond` / etc., the value is timezone-agnostic — skip.
        tail = text[m.end():m.end() + 60]
        if EPOCH_ACCESSOR_RE.match(tail):
            continue
        # Skip when the call sits as the value of a storage-timestamp named
        # argument: prior characters look like `updatedAt = ` or
        # `updatedAt = Some(` etc.
        prefix = text[max(0, abs_off - 64):abs_off]
        if STORAGE_TS_NAMED_ARG_RE.search(prefix):
            continue
        # iter-19: .getOrElse(DateTime.now()) — caller-supplied value is the
        # real intent, this is just the fallback default.
        # iter-20: BUT only skip if followed by explicit `.withZone(...)` or
        # the fallback IS the entire returned value (not flowing into a query).
        # Otherwise the fallback inherits local TZ and feeds downstream code
        # the same way a bare `now()` would.
        if GETORELSE_FALLBACK_RE.search(prefix):
            # Look ahead for `.withZone(`, `.withTimeZone(`, or a closing `)`
            # immediately after `now())` (i.e., the getOrElse is the final
            # statement, not feeding into a calendar query).
            ahead = text[m.end():m.end() + 200]
            if re.search(r"\.\s*with(?:Zone|TimeZone)\b", ahead):
                continue  # rezoned downstream — safe to skip
            # If there's no .withZone follow-up, the fallback IS the bug:
            # local-tz Date flows into whatever consumes the getOrElse result.
            # FALL THROUGH — report this as a finding.
        # Skip positional `Some(<Type>.now())` wrapped values whose trailing
        # context is `))` (closing the wrapping constructor) — this is the
        # canonical "trailing storage timestamp" idiom in our codebase.
        tail2 = text[m.end():m.end() + 6]
        if prefix.rstrip().endswith("Some(") and tail2.startswith(")"):
            continue
        if prefix.rstrip().endswith("Option(") and tail2.startswith(")"):
            continue
        # Skip when `.now()` is followed by `,\n` (positional last/middle
        # constructor arg) AND the preceding char isn't `(` (i.e., it's
        # not the sole argument). Heuristic for case-class trailing timestamps.
        if re.match(r"\s*,\s*\n", tail2):
            stripped = prefix.rstrip()
            if stripped and stripped[-1] not in "(=":
                continue
        line = text.count("\n", 0, abs_off) + 1
        snippet = text[
            max(0, abs_off - 40):abs_off + 80
        ].replace("\n", " ").strip()
        type_name = m.group(1)
        msg = (
            f"`{type_name}.now()` is called without an explicit timezone/zone "
            f"argument in calendar/availability code. This inherits the JVM's "
            f"default timezone and has caused DST/cross-region bugs. Pass "
            f"`DateTimeZone.UTC` (Joda) or a `ZoneId` (java.time) explicitly."
        )
        hits.append((line, snippet, msg))
    return hits


# --- TryOptionUnwrappedAccess -----------------------------------------------
# Look for: accessing collection methods (`.size`, `.length`, `.head`, `.tail`) on identifiers that
# ARE UNAMBIGUOUSLY Try/Option-typed.
# NOTE: `.isEmpty` and `.nonEmpty` are VALID on Try/Option — they return Boolean.
# Only flag methods that Try/Option don't have: `.size`, `.length`, `.head`, `.tail`, `.last`, `.init`
COLLECTION_METHODS = r"(?:size|length|head|tail|last|init)"

# ITER-35: Ultra-conservative heuristic to detect Try/Option access without unwrapping.
# Problem in iter-32 and iter-35: regex matched `result`, `finalResult`, `maybeCashierPay` — these were Seq/List types
# Root cause: WITHOUT semantic analysis, can't distinguish Try/Option from Seq/List
# This rule has fundamental limitations. Accept VERY high FP rate OR make pattern extremely conservative.
# Conservative approach: only match UNAMBIGUOUS Try/Option naming patterns
# Match patterns:
# - Variables starting with: try*, opt*, attempt* (STRONG signals, standard Try/Option naming)
# - Variables containing: Try, Option, Attempt with capital letters (STRONG signals)
# - Removed: result*, maybe*, option (too generic, too many FPs on actual List/Map/Seq variables)
# Known limitation: this captures <10% of intended violations due to conservative approach,
# but also has <10% FP rate (vs. ~100% FP in iter-32).
TRY_OPTION_UNWRAP_RE = re.compile(
    r"\b((?:try|opt|attempt)[a-zA-Z0-9]*|[a-z][a-z0-9]*(?:Try|Option|Attempt)[A-Za-z0-9]*)\s*\.(" + COLLECTION_METHODS + r")\b"
)


def scan_try_option_unwrapped_access(path: Path, text: str) -> list[tuple[int, str, str]]:
    """Detect calls to collection/accessor methods on Try/Option without unwrapping.

    ITER-34: More conservative heuristic to reduce false positives.
    Only matches variables with unambiguous Try/Option indicators (Try, Option, Attempt suffixes,
    or try/opt/attempt/maybe prefixes). Excludes generic names like 'result' or 'finalResult'
    which are commonly used for any computation result (including Seq/List from .take(), .filter(), etc.).
    """
    hits: list[tuple[int, str, str]] = []

    for m in TRY_OPTION_UNWRAP_RE.finditer(text):
        var_name = m.group(1)
        method = m.group(2)

        # Check if there's an unwrapping method call on this identifier within 100 chars before
        context_start = max(0, m.start() - 100)
        context = text[context_start:m.end()]
        # Look for unwrap pattern: if we find one, skip (correctly unwrapped)
        if re.search(rf"\b{re.escape(var_name)}\s*\.\s*(?:map|flatMap|fold|getOrElse|get|recover|tap|foreach)\b", context):
            continue

        abs_off = m.start()
        line = text.count("\n", 0, abs_off) + 1
        snippet = text[abs_off : abs_off + 200].replace("\n", " ").strip()
        msg = (
            f"Calling `.{method}` on `{var_name}` (Try/Option-like name) without unwrapping. "
            f"Try/Option don't have `.{method}` — use `.map(_.{method})`, `.fold(..., _.{method})`, "
            f"or `.getOrElse` to unwrap first."
        )
        hits.append((line, snippet, msg))
    return hits


SPECIALIZED_EMULATORS = {
    "MissingWithAdapterIdentity": scan_missing_with_adapter_identity,
    "StatusRuntimeExceptionForBusinessError": scan_status_runtime_business_error,
    "UnclampedOpenSpots": scan_unclamped_open_spots,
    "MissingDollarInInterpolation": scan_missing_dollar_interpolation,
    "BrokenInterpolationFieldAccess": scan_broken_interpolation_field_access_v2,
    "StaffQueryMissingAppDefId": scan_staff_query_missing_appdefid,
    "CalendarNowWithoutExplicitTimezone": scan_calendar_now_no_tz,
    # ITER-36: TryOptionUnwrappedAccess implemented as scalafix SemanticRule.
    # Semantic rule has access to type information via SemanticDocument, eliminating FPs.
    # Note: SemanticRule requires semantic db to be built (scalafix --tool-classpath
    # with semanticdb compiler plugin). When used, this rule WILL replace the regex emulator.
    # "TryOptionUnwrappedAccess": scan_try_option_unwrapped_access,  # Disabled in favor of SemanticRule
}


def generic_keyword_scan(
    path: Path, text: str, rule: RuleSpec
) -> list[tuple[int, str, str]]:
    """Fallback scanner: use rule.regex_hint, else mine diagnostic_keywords."""
    pattern: re.Pattern | None = None
    if rule.regex_hint:
        try:
            pattern = re.compile(rule.regex_hint)
        except re.error:
            pattern = None
    if pattern is None and rule.diagnostic_keywords:
        # Derive a coarse pattern: pull capitalised identifiers from the first
        # diagnostic message and OR them together.
        toks: list[str] = []
        for kw in rule.diagnostic_keywords:
            for tok in re.findall(r"[A-Za-z_][A-Za-z_0-9]{3,}", kw):
                if tok[0].isupper() and tok not in toks:
                    toks.append(tok)
        if toks:
            try:
                pattern = re.compile(r"\b(?:" + "|".join(toks[:6]) + r")\b")
            except re.error:
                pattern = None
    if pattern is None:
        return []
    hits: list[tuple[int, str, str]] = []
    for m in pattern.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        snippet = text[m.start() : m.start() + 200].replace("\n", " ").strip()
        hits.append((line, snippet, f"{rule.name}: candidate match for `{m.group(0)}`"))
    return hits


def run_regex_emulator(
    rules: list[RuleSpec], files: list[Path], repo: Path
) -> list[Finding]:
    findings: list[Finding] = []
    for f in files:
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        # iter-20: pass REPO-RELATIVE path to scanners. The previous behavior
        # passed absolute paths like `/Users/.../scheduler/...` which made
        # calendar-tz's `path contains "scheduler"` check trivially true on
        # every file. Use the relative path for path-pattern matching.
        rel_f = f.relative_to(repo) if f.is_relative_to(repo) else f

        # iter-45: Skip test files to reduce false positive contamination
        # (40-67% of findings are in test files; excluding reduces noise significantly)
        rel_path_str = str(rel_f)
        if '/test/' in rel_path_str or '/it/' in rel_path_str or rel_path_str.endswith('Test.scala'):
            continue

        for rule in rules:
            scanner = SPECIALIZED_EMULATORS.get(rule.name)
            if scanner is not None:
                hits = scanner(rel_f, text)
            else:
                hits = generic_keyword_scan(rel_f, text, rule)
            for line, snippet, msg in hits:
                findings.append(
                    Finding(
                        rule=rule.name,
                        severity=rule.severity,
                        file=str(f.relative_to(repo)) if f.is_relative_to(repo) else str(f),
                        line=line,
                        snippet=snippet,
                        message=msg,
                        citations=[asdict(c) for c in rule.citations],
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# sbt sweep (opt-in)
# ---------------------------------------------------------------------------

# Parses the sbt-scalafix diagnostic format produced by `<project>/scalafix --check`:
#   [error] /abs/path/File.scala:LINE:COL: error: [RuleName.subRule] message...
# We capture path, line, column, the top-level rule name (before the first `.`)
# and the message. Continuation lines (the offending source + caret) are picked
# up via a follow-up scan.
SBT_DIAG_RE = re.compile(
    r"^\[(?:warn|error)\]\s+(?P<path>\S+\.scala):(?P<line>\d+):(?P<col>\d+):\s+"
    r"(?:error|warning):\s+\[(?P<rule>[\w-]+)(?:\.[\w-]+)?\]\s+(?P<msg>.*)$",
    re.M,
)


def _resolve_rules_jar(sbt_project: Path) -> Path | None:
    """Return the most recent rules JAR produced by `sbt rules/package`."""
    cand = sbt_project / "rules" / "target"
    if not cand.exists():
        return None
    jars = list(cand.rglob("rules_*.jar"))
    # Prefer the non-sources, non-javadoc artifact
    jars = [j for j in jars if "sources" not in j.name and "javadoc" not in j.name]
    if not jars:
        return None
    jars.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return jars[0]


def _publish_rules_locally(sbt_project: Path, sbt_timeout: int) -> bool:
    """Run `sbt rules/publishLocal` so the rules artifact is resolvable via Ivy.

    Required because sbt-scalafix loads custom rule jars through coursier, which
    expects published Maven/Ivy coordinates — it doesn't honor `from <url>`.
    """
    print(f"[scan] publishing rules locally in {sbt_project}", file=sys.stderr)
    try:
        proc = subprocess.run(
            ["sbt", "-batch", "-no-colors", "rules/publishLocal"],
            cwd=str(sbt_project),
            capture_output=True,
            text=True,
            timeout=sbt_timeout,
        )
    except FileNotFoundError:
        print("[scan] sbt not on PATH — cannot run --use-sbt", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print(f"[scan] sbt rules/publishLocal timed out after {sbt_timeout}s",
              file=sys.stderr)
        return False
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).splitlines()[-15:]
        print("[scan] rules/publishLocal failed:\n  " + "\n  ".join(tail),
              file=sys.stderr)
        return False
    return True


def _detect_sbt_project_layout(sbt_project: Path) -> tuple[str, str] | None:
    """Return (target_project_name, scan_label) for the scalafix target.

    The rule-validator's testkit layout exposes the inputs under the `input`
    project. Future repos that wire the rules plugin natively will likely use
    their main project name — callers can override via `--sbt-target-project`.
    """
    build_sbt = sbt_project / "build.sbt"
    if not build_sbt.exists():
        return None
    txt = build_sbt.read_text(errors="replace")
    if 'project in file("input")' in txt:
        return ("input", "rule-validator/input")
    # Heuristic for downstream repos: scalafix the root project
    return ("", "root")


def run_sbt_scalafix(
    target_repo: Path,
    rules: list[RuleSpec],
    sbt_project: Path,
    sbt_timeout: int,
    sbt_target_project: str | None = None,
) -> list[Finding]:
    """Invoke the real `sbt scalafix --check` on `sbt_project` using our rules.

    The rules jar is `publishLocal`-published, then scalafix is run with
    `scalafixDependencies` augmented to include the published artifact. All
    rule names registered in `META-INF/services/scalafix.v1.Rule` become
    invokable by short name.

    NOTE: `target_repo` is recorded in the report but the actual scan is
    performed against `sbt_project`'s configured sources (the testkit's
    `input/` directory by default). Scanning an arbitrary external repo
    requires that repo to have its own sbt-scalafix wiring — see the
    `--sbt-project` docstring above.
    """
    if not sbt_project.exists():
        print(f"[scan] --sbt-project does not exist: {sbt_project}",
              file=sys.stderr)
        return []
    if not (sbt_project / "build.sbt").exists():
        print(f"[scan] --sbt-project has no build.sbt: {sbt_project}",
              file=sys.stderr)
        return []

    if not _publish_rules_locally(sbt_project, sbt_timeout):
        return []

    jar = _resolve_rules_jar(sbt_project)
    if jar is None:
        print("[scan] could not locate the packaged rules jar after publish",
              file=sys.stderr)
        return []
    print(f"[scan] rules jar: {jar}", file=sys.stderr)

    if sbt_target_project is None:
        layout = _detect_sbt_project_layout(sbt_project)
        if layout is None:
            print("[scan] could not detect sbt project layout", file=sys.stderr)
            return []
        sbt_target_project, label = layout
    else:
        label = sbt_target_project or "root"
    target_prefix = f"{sbt_target_project}/" if sbt_target_project else ""

    rule_args = " ".join(r.name for r in rules)
    # Set scalafixDependencies via `from URL` so the published artifact is
    # picked up regardless of organization — coursier resolves through Ivy
    # local first, so the `publishLocal` step above is what makes this work.
    sbt_cmd = (
        "; "
        'set ThisBuild/scalafixDependencies += "rules" %% "rules" % "0.1.0-SNAPSHOT"'
        f"; {target_prefix}scalafix --check {rule_args}"
    )
    cmd = ["sbt", "-batch", "-no-colors", sbt_cmd]
    print(f"[scan] running scalafix --check on {label} (project={sbt_project})",
          file=sys.stderr)
    try:
        proc = subprocess.run(
            cmd, cwd=str(sbt_project), capture_output=True, text=True,
            timeout=sbt_timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"[scan] sbt scalafix timed out after {sbt_timeout}s",
              file=sys.stderr)
        return []
    except FileNotFoundError:
        print("[scan] sbt not on PATH", file=sys.stderr)
        return []
    # Non-zero exit is expected when --check finds violations.
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if "scalafix.sbt.InvalidArgument" in out and "Unknown rule" in out:
        print("[scan] scalafix could not resolve our rule names — "
              "is the rules jar publishLocal'd?", file=sys.stderr)
        return []

    findings: list[Finding] = []
    rules_by_name = {r.name: r for r in rules}
    # Walk the matches line-by-line so we can grab the next non-empty line as
    # the offending source snippet (sbt-scalafix always prints it underneath).
    lines = out.splitlines()
    for i, line in enumerate(lines):
        m = SBT_DIAG_RE.match(line)
        if not m:
            continue
        path = m.group("path")
        line_no = int(m.group("line"))
        rule_name = m.group("rule")
        msg = m.group("msg").strip()
        # Snippet: next [error]/[warn] line that doesn't have file:line:col on it
        snippet = ""
        for j in range(i + 1, min(len(lines), i + 4)):
            cand = lines[j].strip()
            if cand.startswith("[error]") or cand.startswith("[warn]"):
                body = cand.split("]", 1)[1].strip() if "]" in cand else cand
                # Skip caret-only lines
                if body and not set(body) <= set("^ "):
                    snippet = body[:200]
                    break
        rule = rules_by_name.get(rule_name)
        sev = rule.severity if rule else "medium"
        cites = [asdict(c) for c in rule.citations] if rule else []
        # Try to render the path relative to the target repo for readability.
        try:
            rel = str(Path(path).resolve().relative_to(target_repo.resolve()))
        except (ValueError, OSError):
            try:
                rel = str(Path(path).resolve().relative_to(sbt_project.resolve()))
            except (ValueError, OSError):
                rel = path
        findings.append(
            Finding(
                rule=rule_name,
                severity=sev,
                file=rel,
                line=line_no,
                snippet=snippet,
                message=msg,
                citations=cites,
            )
        )
    print(f"[scan] sbt scalafix produced {len(findings)} finding(s)",
          file=sys.stderr)
    return findings


# ---------------------------------------------------------------------------
# Deep agent-driven scan (stubbed)
# ---------------------------------------------------------------------------

def run_deep_prefilter(
    rules: list[RuleSpec], repo: Path, paths: list[str]
) -> list[Finding]:
    findings: list[Finding] = []
    for rule in rules:
        hint = rule.regex_hint
        if not hint and rule.diagnostic_keywords:
            toks = [t for kw in rule.diagnostic_keywords for t in re.findall(r"\w{5,}", kw)]
            if toks:
                hint = "|".join(sorted(set(toks))[:5])
        if not hint:
            continue
        cmd = ["rg", "-n", "--no-heading", "-e", hint]
        for pat in paths or ["*.scala"]:
            # ripgrep uses --glob
            cmd.extend(["--glob", pat])
        cmd.append(str(repo))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        for line in proc.stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            fp, ln, body = parts
            try:
                line_no = int(ln)
            except ValueError:
                continue
            try:
                rel = str(Path(fp).resolve().relative_to(repo.resolve()))
            except ValueError:
                rel = fp

            # iter-45: Skip test files to reduce false positive contamination
            if '/test/' in rel or '/it/' in rel or rel.endswith('Test.scala'):
                continue

            findings.append(
                Finding(
                    rule=rule.name,
                    severity=rule.severity,
                    file=rel,
                    line=line_no,
                    snippet=body[:200],
                    message=f"pending_llm_review: candidate match for {rule.name}",
                    citations=[asdict(c) for c in rule.citations],
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def filter_severity(findings: list[Finding], minimum: str) -> list[Finding]:
    threshold = SEVERITY_ORDER.get(minimum, 2)
    return [f for f in findings if SEVERITY_ORDER.get(f.severity, 1) <= threshold]


def build_summary(findings: list[Finding], rules: list[RuleSpec]) -> dict:
    by_rule: dict[str, int] = {r.name: 0 for r in rules}
    by_sev: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    return {"by_rule": by_rule, "by_severity": by_sev, "total": len(findings)}


def write_markdown(report: dict, path: Path) -> None:
    badge = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}
    lines: list[str] = []
    lines.append(f"# Scan report: {report['repo']}")
    lines.append("")
    lines.append(f"- Scanned at: {report['scanned_at']}")
    lines.append(f"- Rules: {', '.join(report['rules_run']) or '(none)'}")
    lines.append(f"- Total findings: {report['summary']['total']}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Rule | Count | Severity |")
    lines.append("|------|-------|----------|")
    sev_by_rule = {r["name"]: r["severity"] for r in report["rule_meta"]}
    for rule, count in report["summary"]["by_rule"].items():
        lines.append(f"| {rule} | {count} | {sev_by_rule.get(rule, 'medium')} |")
    lines.append("")
    lines.append("## Findings by rule")
    by_rule: dict[str, list[dict]] = {}
    for f in report["findings"]:
        by_rule.setdefault(f["rule"], []).append(f)
    for rule_name, items in by_rule.items():
        lines.append("")
        lines.append(f"### {rule_name} ({len(items)} findings)")
        # citations once per rule
        cites = items[0].get("citations") or []
        if cites:
            lines.append("")
            lines.append("**Origin PRs:**")
            for c in cites:
                t = f" — {c['title']}" if c.get("title") else ""
                lines.append(f"- {c['pr_url']}{t}")
        lines.append("")
        for f in items[:50]:
            b = badge.get(f["severity"], "[MED]")
            lines.append(f"- {b} `{f['file']}:{f['line']}` — {f['message']}")
        if len(items) > 50:
            lines.append(f"- ... ({len(items) - 50} more truncated)")
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-path", required=True, type=Path)
    ap.add_argument("--rules-dir", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--paths", action="append", default=[],
                    help="glob (relative to repo). May be passed multiple times.")
    ap.add_argument("--paths-exclude", action="append", default=[],
                    help="glob to exclude (relative to repo). May be passed multiple times. "
                         "Useful for docs/examples paths that aren't production code.")
    ap.add_argument("--severity-min", default="low", choices=["high", "medium", "low"])
    ap.add_argument("--use-sbt", action="store_true",
                    help="Run real sbt scalafix sweep (slow). Default: regex emulator.")
    ap.add_argument("--sbt-project", type=Path,
                    default=Path("rule-validator"),
                    help="Path to an sbt project that has our rules wired in. "
                         "Defaults to rule-validator/. Scanning an arbitrary "
                         "repo requires that repo to have sbt-scalafix + the "
                         "rules artifact configured.")
    ap.add_argument("--sbt-target-project", type=str, default=None,
                    help="sbt project name within --sbt-project to run "
                         "scalafix against (default: auto-detect; uses `input` "
                         "for the rule-validator layout).")
    ap.add_argument("--sbt-timeout", type=int, default=600,
                    help="Timeout (s) for each sbt invocation. Default 600.")
    ap.add_argument("--rules-only-fast", action="store_true",
                    help="Force fast regex emulator (default). Kept for CLI compat.")
    ap.add_argument("--deep", action="store_true",
                    help="Also run the ripgrep-based deep pre-filter for agent review.")
    ap.add_argument("--include-tests", action="store_true",
                    help="Include test paths in the scan (default: excluded)")
    ap.add_argument("--rationale-roots", action="append", default=[],
                    help="Additional dirs to scan for rationale.md files.")
    ap.add_argument("--no-yaml", action="store_true",
                    help="Disable Semgrep/Opengrep YAML rule execution.")
    ap.add_argument("--semgrep-bin", type=str, default="",
                    help="Path to semgrep binary (default: auto-detect).")
    ap.add_argument("--github-org", default=_DEFAULT_GITHUB_ORG,
                    help="GitHub org for parsing PR citations in rule rationales.")
    ap.add_argument("--repo-hint", default="backend",
                    help="Default repo name when rationales cite bare PR numbers.")
    ap.add_argument("--language", default="auto",
                    choices=["auto", "scala", "opengrep"],
                    help="Rule engine filter: auto-detect from file extensions, or force scala/opengrep.")
    args = ap.parse_args(argv)

    t0 = time.time()
    repo = args.repo_path
    if not repo.exists():
        print(f"ERROR: repo-path does not exist: {repo}", file=sys.stderr)
        return 2
    rules_dir = args.rules_dir
    if not rules_dir.exists():
        print(f"ERROR: rules-dir does not exist: {rules_dir}", file=sys.stderr)
        return 2

    # Default rationale roots
    default_roots = [
        Path("out/candidates_v2"),
        Path("out/candidates"),
    ]
    rationale_roots = [Path(p) for p in args.rationale_roots] + default_roots
    rationale_roots = [p.resolve() for p in rationale_roots]

    rules = discover_rules(rules_dir, rationale_roots, github_org=args.github_org, repo_hint=args.repo_hint)
    if not rules:
        print(f"WARNING: no rules discovered under {rules_dir}", file=sys.stderr)

    print(f"[scan] discovered {len(rules)} rule(s): "
          f"{', '.join(r.name for r in rules)}", file=sys.stderr)

    findings: list[Finding] = []
    if args.use_sbt and not args.rules_only_fast:
        findings.extend(
            run_sbt_scalafix(
                repo,
                rules,
                sbt_project=args.sbt_project.resolve(),
                sbt_timeout=args.sbt_timeout,
                sbt_target_project=args.sbt_target_project,
            )
        )
    else:
        files = enumerate_files(repo, args.paths, include_tests=args.include_tests, excludes=args.paths_exclude)
        print(f"[scan] enumerated {len(files)} candidate files", file=sys.stderr)
        findings.extend(run_regex_emulator(rules, files, repo))

    # YAML (Semgrep/Opengrep) rules — run unless disabled.
    yaml_rule_names: list[str] = []
    if not args.no_yaml:
        yaml_rules = discover_yaml_rules(rules_dir)
        if yaml_rules:
            for yp in yaml_rules:
                yaml_rule_names.extend(_yaml_rule_ids(yp))
            print(f"[scan] discovered {len(yaml_rules)} YAML rule file(s) "
                  f"with rule ids: {', '.join(yaml_rule_names) or '(none)'}",
                  file=sys.stderr)
            # Resolve semgrep binary: explicit > PATH > sys.executable sibling
            semgrep_bin = args.semgrep_bin
            if not semgrep_bin:
                # Prefer one alongside the running python (venv install)
                cand = Path(sys.executable).parent / "semgrep"
                semgrep_bin = str(cand) if cand.exists() else "semgrep"
            findings.extend(
                run_semgrep_yaml(yaml_rules, repo, args.paths, semgrep_bin)
            )

    if args.deep:
        findings.extend(run_deep_prefilter(rules, repo, args.paths))

    findings = filter_severity(findings, args.severity_min)
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 1), f.file, f.line))

    summary = build_summary(findings, rules)
    # Ensure YAML rule ids appear in the summary even with zero findings.
    for rid in yaml_rule_names:
        summary["by_rule"].setdefault(rid, 0)
    report = {
        "scanned_at": _dt.datetime.utcnow().isoformat() + "Z",
        "repo": str(repo),
        "rules_run": [r.name for r in rules] + yaml_rule_names,
        "rule_meta": [
            {
                "name": r.name,
                "severity": r.severity,
                "rationale_path": r.rationale_path,
                "citations": [asdict(c) for c in r.citations],
            }
            for r in rules
        ],
        "findings": [asdict(f) for f in findings],
        "summary": summary,
        "runtime_seconds": round(time.time() - t0, 3),
    }

    out_path = args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    md_path = out_path.with_suffix(".md")
    write_markdown(report, md_path)

    print(
        f"[scan] {len(findings)} finding(s) -> {out_path} ({md_path}) "
        f"in {report['runtime_seconds']}s",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
