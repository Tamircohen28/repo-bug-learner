#!/usr/bin/env python3
"""Standalone rule-dedup gate.

Walks integrated rules and candidate rules, extracts a pattern fingerprint
and an AST anchor set per rule, and flags candidates that EXACTLY duplicate
or substantially OVERLAP already-integrated rules (or other candidates).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# --- extraction helpers ------------------------------------------------------

_CLASS_RE = re.compile(
    r"class\s+(\w+)\s+extends\s+(?:Syntactic|Semantic)Rule\s*\(",
)
_DIAG_ID_RE = re.compile(r"Diagnostic\s*\(\s*(?:id\s*=\s*)?\"([^\"]+)\"")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_WS_RE = re.compile(r"\s+")

# AST-ish anchor extractors
_TERM_NAME_RE = re.compile(r"Term\.Name\s*\(\s*\"([^\"]+)\"\s*\)")
_TYPE_NAME_RE = re.compile(r"Type\.Name\s*\(\s*\"([^\"]+)\"\s*\)")
_ENDS_WITH_RE = re.compile(r"endsWith\s*\(\s*\"([^\"]+)\"\s*\)")
_STARTS_WITH_RE = re.compile(r"startsWith\s*\(\s*\"([^\"]+)\"\s*\)")
_STRING_LIT_RE = re.compile(r"\"([^\"\n]{2,})\"")


def _strip_comments(src: str) -> str:
    src = _BLOCK_COMMENT_RE.sub("", src)
    src = _LINE_COMMENT_RE.sub("", src)
    return src


def pattern_fingerprint(src: str) -> str:
    stripped = _strip_comments(src)
    normalized = _WS_RE.sub("", stripped)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


# Tokens we don't want polluting the anchor set (boilerplate / framework)
_NOISE = {
    "fix", "doc", "tree", "pos", "init", "rhs", "values", "args", "argss",
    "argClauses", "other", "t", "n", "id", "message", "position", "lint",
    "empty", "collect", "exists", "flatten", "map", "flatMap", "nonEmpty",
    "true", "false", "Some", "None", "Seq", "Set", "List", "String", "Boolean",
    "Tree", "Term", "Type", "Patch", "Diagnostic", "SyntacticDocument",
    "SemanticDocument", "implicit",
}


def anchor_set(src: str) -> set[str]:
    stripped = _strip_comments(src)
    anchors: set[str] = set()
    for rx in (_TERM_NAME_RE, _TYPE_NAME_RE, _ENDS_WITH_RE, _STARTS_WITH_RE):
        anchors.update(rx.findall(stripped))
    # add meaningful string literals (limit to identifier-ish words)
    for lit in _STRING_LIT_RE.findall(stripped):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", lit):
            anchors.add(lit)
    return {a for a in anchors if a not in _NOISE}


def extract_class_name(src: str) -> str | None:
    m = _CLASS_RE.search(src)
    return m.group(1) if m else None


def extract_diagnostic_id(src: str) -> str | None:
    m = _DIAG_ID_RE.search(src)
    return m.group(1) if m else None


# --- rule containers ---------------------------------------------------------


@dataclass
class Rule:
    path: Path
    class_name: str
    diagnostic_id: str | None
    fingerprint: str
    anchors: set[str] = field(default_factory=set)


def load_rule(path: Path) -> Rule | None:
    src = path.read_text(encoding="utf-8", errors="replace")
    cname = extract_class_name(src)
    if not cname:
        return None
    diag = extract_diagnostic_id(src)
    anchors = anchor_set(src)
    # Strip self-referential identifiers — the class name and its diagnostic id
    # are almost never shared across rules and only deflate the Jaccard score
    # for genuinely overlapping rules.
    anchors.discard(cname)
    if diag:
        anchors.discard(diag)
    return Rule(
        path=path,
        class_name=cname,
        diagnostic_id=diag,
        fingerprint=pattern_fingerprint(src),
        anchors=anchors,
    )


def walk_integrated(root: Path) -> list[Rule]:
    rules: list[Rule] = []
    for p in sorted(root.rglob("*.scala")):
        r = load_rule(p)
        if r is not None:
            rules.append(r)
    return rules


def walk_candidates(root: Path) -> list[Rule]:
    rules: list[Rule] = []
    for p in sorted(root.rglob("Rule.scala")):
        r = load_rule(p)
        if r is not None:
            rules.append(r)
    return rules


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


# --- dedup logic -------------------------------------------------------------

OVERLAP_THRESHOLD = 0.6


def classify(
    candidate: Rule,
    integrated: Iterable[Rule],
    other_candidates: Iterable[Rule],
) -> tuple[str, list[str], float]:
    # EXACT pattern match against integrated
    for r in integrated:
        if r.fingerprint == candidate.fingerprint:
            return "EXACT", [r.class_name], 1.0

    best_score = 0.0
    best_overlaps: list[tuple[str, float]] = []

    for pool in (integrated, other_candidates):
        for r in pool:
            if r.path == candidate.path:
                continue
            score = jaccard(candidate.anchors, r.anchors)
            if score >= OVERLAP_THRESHOLD:
                best_overlaps.append((r.class_name, score))
                if score > best_score:
                    best_score = score

    if best_overlaps:
        # de-dupe while preserving order, sorted by score desc
        seen: set[str] = set()
        ordered = sorted(best_overlaps, key=lambda x: -x[1])
        names: list[str] = []
        for name, _ in ordered:
            if name not in seen:
                seen.add(name)
                names.append(name)
        return "OVERLAP", names, round(best_score, 3)

    return "DISTINCT", [], 0.0


def write_dedup_md(candidate: Rule, verdict: str, overlaps: list[str], score: float) -> None:
    md_path = candidate.path.parent / "dedup.md"
    body = [
        f"# Dedup verdict: {verdict}",
        "",
        f"- candidate class: `{candidate.class_name}`",
        f"- candidate path: `{candidate.path}`",
        f"- diagnostic id: `{candidate.diagnostic_id}`",
        f"- fingerprint: `{candidate.fingerprint}`",
        f"- jaccard: `{score}`",
        f"- overlaps with: {', '.join(f'`{o}`' for o in overlaps) if overlaps else '(none)'}",
        "",
        "This rule was auto-flagged by `scripts/dedup_rules.py` because its "
        "AST anchor set is substantially similar to an already-integrated "
        "rule (or its pattern fingerprint matches exactly). Review before "
        "integrating; consider merging anchors into the existing rule "
        "instead of adding a duplicate.",
        "",
    ]
    md_path.write_text("\n".join(body), encoding="utf-8")


# --- CLI ---------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Rule-dedup gate")
    ap.add_argument("--candidates", required=True, type=Path)
    ap.add_argument("--integrated", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    integrated = walk_integrated(args.integrated)
    candidates = walk_candidates(args.candidates)

    candidate_records = []
    counts = {"EXACT": 0, "OVERLAP": 0, "DISTINCT": 0}

    for cand in candidates:
        verdict, overlaps, score = classify(cand, integrated, candidates)
        counts[verdict] += 1
        candidate_records.append({
            "candidate_path": str(cand.path),
            "class_name": cand.class_name,
            "diagnostic_id": cand.diagnostic_id,
            "fingerprint": cand.fingerprint,
            "verdict": verdict,
            "overlaps_with": overlaps,
            "jaccard": score,
        })
        if verdict in ("EXACT", "OVERLAP"):
            write_dedup_md(cand, verdict, overlaps, score)

    report = {
        "integrated_rules": [
            {
                "path": str(r.path),
                "class_name": r.class_name,
                "diagnostic_id": r.diagnostic_id,
                "fingerprint": r.fingerprint,
                "anchor_count": len(r.anchors),
            }
            for r in integrated
        ],
        "candidate_rules": candidate_records,
        "summary": {
            "integrated_count": len(integrated),
            "candidate_count": len(candidates),
            **counts,
            "overlap_threshold": OVERLAP_THRESHOLD,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        f"integrated={len(integrated)} candidates={len(candidates)} "
        f"EXACT={counts['EXACT']} OVERLAP={counts['OVERLAP']} DISTINCT={counts['DISTINCT']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
