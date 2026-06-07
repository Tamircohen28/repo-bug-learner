#!/usr/bin/env python3
"""
Permanent multi-seed verification helper.

Reads a scan-findings JSON (shape produced by scripts/scan_repo.py:
top-level `findings` list of {rule,severity,file,line,snippet,...}),
filters to one rule, draws random samples under multiple seeds, takes
the union of sampled finding indices, and emits a Markdown "verify
cards" document with one block per unique finding for hand-classification.

If the total number of findings for the rule is <= n, sampling is skipped
and ALL findings are emitted (no seeds needed).

Usage:
    python scripts/verify_multiseed.py \\
        --findings out/iterations/scan_iter17_scheduler.json \\
        --rule MissingWithAdapterIdentity \\
        --seeds 42,20260521,20260521_v2 \\
        --n 10 \\
        --repo-path /Users/tamirc/IdeaProjects/scheduler \\
        --output out/iterations/multiseed_<rule>.md

The `<rule>` token in --output is substituted with the rule name.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------

def _seed_to_int(seed: str) -> int:
    """Accept either an int-like seed or any string; hash strings to int."""
    try:
        return int(seed)
    except ValueError:
        return int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % (2**32)


def _read_context(repo_path: Path, rel_file: str, line: int, ctx: int = 15) -> str:
    """Return ~30 lines of source context centered on `line` (1-indexed)."""
    candidates = [repo_path / rel_file, Path(rel_file)]
    src: Path | None = None
    for c in candidates:
        if c.is_file():
            src = c
            break
    if src is None:
        return f"[file not found: {rel_file}]"
    try:
        text = src.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:  # pragma: no cover
        return f"[read error: {e}]"
    lo = max(1, line - ctx)
    hi = min(len(text), line + ctx)
    out: list[str] = []
    for i in range(lo, hi + 1):
        marker = ">>" if i == line else "  "
        out.append(f"{marker} {i:5d}  {text[i-1]}")
    return "\n".join(out)


def _heuristic_verdict(finding: dict[str, Any], context: str) -> tuple[str, str]:
    """A very lightweight TP/FP/AMBIG suggestion. Caller should still verify.

    Heuristics (intentionally conservative — defaults to AMBIG):
    - test-y paths => FP
    - 'TODO'/'FIXME' in nearby context => AMBIG (could be known)
    - rule snippet looks like it's inside a comment => FP
    - else => AMBIG
    """
    f = finding.get("file", "").lower()
    test_markers = ("test", "spec", "mock", "stub", "testkit", "fixture", "__tests__")
    if any(m in f for m in test_markers):
        return "FP", "path contains test/spec/mock marker"
    snippet = finding.get("snippet", "").strip()
    if snippet.startswith("//") or snippet.startswith("/*") or snippet.startswith("*"):
        return "FP", "snippet looks like a comment"
    if "TODO" in context or "FIXME" in context:
        return "AMBIG", "TODO/FIXME nearby — may be known"
    # severity high + non-test => lean TP suggestion
    if finding.get("severity") == "high":
        return "AMBIG", "high-severity, non-test path — likely TP but verify"
    return "AMBIG", "no signal — please inspect manually"


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--findings", required=True, help="Path to scan-findings JSON")
    ap.add_argument("--rule", required=True, help="Rule name to filter on")
    ap.add_argument("--seeds", default="42,20260521,20260521_v2",
                    help="Comma-separated list of seeds (int or string)")
    ap.add_argument("--n", type=int, default=10, help="Sample size per seed")
    ap.add_argument("--repo-path", required=True, help="Root path of the scanned repo (for context reads)")
    ap.add_argument("--output", required=True,
                    help="Output .md path. The literal '<rule>' is substituted with the rule name.")
    ap.add_argument("--auto-verify", action="store_true",
                    help="Print heuristic TP/FP/AMBIG suggestions next to each finding")
    args = ap.parse_args()

    findings_path = Path(args.findings)
    if not findings_path.is_file():
        print(f"error: findings file not found: {findings_path}", file=sys.stderr)
        return 2
    data = json.loads(findings_path.read_text())
    all_findings = data.get("findings", data if isinstance(data, list) else [])
    rule_findings = [f for f in all_findings if f.get("rule") == args.rule]
    total = len(rule_findings)

    if total == 0:
        print(f"warning: 0 findings for rule {args.rule!r}", file=sys.stderr)

    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    sampled_indices: list[int]
    per_seed_samples: dict[str, list[int]] = {}

    if total <= args.n:
        sampled_indices = list(range(total))
        sample_note = (
            f"Total findings ({total}) <= n ({args.n}) — sampling skipped, "
            f"verifying ALL findings."
        )
    else:
        union: set[int] = set()
        for s in seeds:
            rng = random.Random(_seed_to_int(s))
            idxs = sorted(rng.sample(range(total), args.n))
            per_seed_samples[s] = idxs
            union.update(idxs)
        sampled_indices = sorted(union)
        sample_note = (
            f"Total findings = {total}; sampled n={args.n} under seeds "
            f"{seeds}; union size = {len(sampled_indices)}."
        )

    out_path = Path(args.output.replace("<rule>", args.rule))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    repo_path = Path(args.repo_path)

    lines: list[str] = []
    lines.append(f"# Multi-Seed Verification — `{args.rule}`")
    lines.append("")
    lines.append(f"- Findings file: `{findings_path}`")
    lines.append(f"- Repo: `{repo_path}`")
    lines.append(f"- Seeds: `{seeds}`")
    lines.append(f"- n per seed: `{args.n}`")
    lines.append(f"- {sample_note}")
    lines.append("")
    if per_seed_samples:
        lines.append("## Per-seed sample indices")
        lines.append("")
        for s, idxs in per_seed_samples.items():
            lines.append(f"- seed `{s}`: {idxs}")
        lines.append("")
    lines.append("## Verdict tally (fill in)")
    lines.append("")
    lines.append("| seed | TP | FP | AMBIG | strict TP% |")
    lines.append("|---|---|---|---|---|")
    for s in (list(per_seed_samples.keys()) + ["UNION"]) if per_seed_samples else ["ALL"]:
        lines.append(f"| {s} |   |   |   |   |")
    lines.append("")
    lines.append("---")
    lines.append("")

    for n_card, idx in enumerate(sampled_indices, start=1):
        f = rule_findings[idx]
        lines.append(f"## Card {n_card} — finding #{idx}")
        lines.append("")
        lines.append(f"- **rule:** `{f.get('rule')}`")
        lines.append(f"- **severity:** `{f.get('severity')}`")
        lines.append(f"- **file:** `{f.get('file')}:{f.get('line')}`")
        if per_seed_samples:
            in_seeds = [s for s, idxs in per_seed_samples.items() if idx in idxs]
            lines.append(f"- **drawn by seeds:** `{in_seeds}`")
        lines.append("")
        lines.append("**message:**")
        lines.append("")
        lines.append("> " + (f.get("message") or "").replace("\n", "\n> "))
        lines.append("")
        lines.append("**context (±15 lines):**")
        lines.append("")
        lines.append("```")
        lines.append(_read_context(repo_path, f.get("file", ""), int(f.get("line", 1)), ctx=15))
        lines.append("```")
        lines.append("")
        if args.auto_verify:
            verdict, why = _heuristic_verdict(f, _read_context(repo_path, f.get("file", ""), int(f.get("line", 1)), ctx=15))
            lines.append(f"**auto-verify (heuristic):** `{verdict}` — {why}")
            lines.append("")
        lines.append("**Verdict:** ☐ TP   ☐ FP   ☐ AMBIG")
        lines.append("")
        lines.append("**Notes:**")
        lines.append("")
        lines.append("---")
        lines.append("")

    out_path.write_text("\n".join(lines))
    print(f"wrote {out_path} ({len(sampled_indices)} unique cards from {total} findings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
