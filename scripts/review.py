"""LLM-friendly review orchestrator for repo-bug-learner rules.

Designed to be called from a Claude Code skill (`.claude/skills/repo-bug-review/`)
or from a developer's terminal. Takes a code input (file / directory / PR / pasted
snippet), runs the rule scanner against it, and writes per-finding "review bundles"
that a downstream LLM can judge.

A review bundle is a markdown file with:
  - The finding (rule, file, line, message)
  - The rule's rationale (origin PRs, FP guards, severity)
  - ±30 lines of file context around the finding
  - A judgment template (TP / FP / SUSPICIOUS + reasoning + suggested fix)

Usage from CLI:
  python scripts/review.py --file /path/to/Foo.scala
  python scripts/review.py --dir /path/to/backend
  python scripts/review.py --pr 30345 --repo your-org/backend
  python scripts/review.py --snippet /tmp/snippet.scala
  python scripts/review.py --snippet-text "...inline code..." --language scala

Output:
  out/review/<timestamp>/
    summary.json         — list of bundles + metadata
    bundles/<n>.md       — one per finding
    INDEX.md             — human-readable overview
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = PROJECT_ROOT / "rule-validator" / "rules"
CANDIDATE_ROOTS = [
    PROJECT_ROOT / "out" / "candidates_v2",
    PROJECT_ROOT / "out" / "candidates_v3",
    PROJECT_ROOT / "out" / "candidates",
    PROJECT_ROOT / "out" / "candidates_cross_repo",
    PROJECT_ROOT / "out" / "candidates_mobile",
]


def _ext_for_language(lang: str) -> str:
    return {
        "scala": ".scala",
        "ts": ".ts",
        "tsx": ".tsx",
        "typescript": ".ts",
        "js": ".js",
        "javascript": ".js",
    }.get(lang.lower(), ".txt")


def _find_rationale(rule_name: str) -> Path | None:
    """Find rationale.md for a given rule name across the candidate trees."""
    for root in CANDIDATE_ROOTS:
        if not root.exists():
            continue
        for r in root.rglob("rationale.md"):
            try:
                if rule_name in r.read_text(errors="replace"):
                    return r
            except OSError:
                continue
    return None


def _context_around(file_path: Path, line: int, before: int = 15, after: int = 15) -> str:
    try:
        lines = file_path.read_text(errors="replace").splitlines()
    except OSError:
        return "(could not read file)"
    start = max(0, line - 1 - before)
    end = min(len(lines), line + after)
    out = []
    for i in range(start, end):
        marker = ">>" if i == line - 1 else "  "
        out.append(f"{marker} {i+1:5d}: {lines[i]}")
    return "\n".join(out)


def run_scan(repo_path: Path, scan_json: Path, paths: list[str] | None = None) -> dict:
    """Invoke scan_repo.py against the given path."""
    venv_py = PROJECT_ROOT / ".venv" / "bin" / "python"
    py = str(venv_py) if venv_py.exists() else sys.executable
    cmd = [
        py, str(PROJECT_ROOT / "scripts" / "scan_repo.py"),
        "--repo-path", str(repo_path),
        "--rules-dir", str(RULES_DIR),
        "--output", str(scan_json),
    ]
    for p in paths or []:
        cmd.extend(["--paths", p])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"scan failed: {proc.returncode}")
    return json.loads(scan_json.read_text())


def build_review_bundle(
    finding: dict, repo_root: Path, idx: int, out_dir: Path
) -> Path:
    """Produce a single review-bundle markdown file for one finding."""
    rule_name = finding["rule"]
    file_rel = finding["file"]
    line = finding["line"]
    file_path = repo_root / file_rel
    if not file_path.exists():
        # Try as-is in case repo_root already prefixed
        file_path = Path(file_rel)

    rationale_path = _find_rationale(rule_name)
    rationale_text = ""
    if rationale_path and rationale_path.exists():
        rationale_text = rationale_path.read_text(errors="replace")

    context = _context_around(file_path, line)
    citations = finding.get("citations") or []
    citation_lines = "\n".join(
        f"- {c.get('pr_url', '')} {c.get('title', '')}".rstrip()
        for c in citations
    ) or "_(no PR citations in rationale)_"

    bundle = f"""# Review bundle #{idx} — {rule_name}

## Finding
- **Rule**: `{rule_name}`
- **Severity**: {finding.get('severity', 'medium')}
- **File**: `{file_rel}`
- **Line**: {line}
- **Snippet**: `{finding.get('snippet', '')[:200]}`
- **Rule message**:
  > {finding.get('message', '')}

## Cited PRs (origin of this rule)
{citation_lines}

## File context (±15 lines)

```
{context}
```

## Rule rationale (excerpt)

{rationale_text[:3000] if rationale_text else "_(no rationale found; see rule source)_"}

---

## Judgment template — fill this in

### Verdict
- [ ] **TP** — this matches the rule's bug class
- [ ] **FP** — rule fired but code is actually fine; explain why
- [ ] **SUSPICIOUS** — not exactly the rule's pattern but concerning; explain

### Reasoning
_(2-4 sentences — what the code actually does, why it matches or doesn't match the rule's intent)_

### Suggested fix (if TP)
_(concrete patch suggestion or describe the safer pattern)_

### Nearby issues
_(while you have the file open, look ±50 lines for OTHER instances of the same bug class that the rule didn't flag — list any)_
"""
    bundle_path = out_dir / f"bundle_{idx:03d}.md"
    bundle_path.write_text(bundle)
    return bundle_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", type=Path, help="single file to review")
    src.add_argument("--dir", type=Path, help="directory to review")
    src.add_argument("--snippet", type=Path, help="file containing pasted code")
    src.add_argument(
        "--snippet-text", type=str,
        help="inline code to review (paired with --language)"
    )
    src.add_argument("--pr", type=str, help="PR number or URL to review")

    ap.add_argument("--repo", type=str, required=False, default=None,
                    help="for --pr, required GitHub repo (owner/name)")
    ap.add_argument("--language", default="scala",
                    help="for --snippet-text (scala/ts/tsx/js)")
    ap.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "out" / "review" / _dt.datetime.now().strftime("%Y%m%d_%H%M%S"),
    )
    args = ap.parse_args()

    if args.pr and not args.repo:
        raise SystemExit("--repo owner/name is required with --pr")

    out_dir = args.output
    bundles_dir = out_dir / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)

    # Resolve input → a directory the scanner can read
    pr_added_ranges: dict[str, list[tuple[int, int]]] | None = None
    if args.file:
        scan_root = args.file.parent
        paths = [args.file.name]
        repo_root = scan_root
    elif args.dir:
        scan_root = args.dir
        paths = None
        repo_root = scan_root
    elif args.snippet:
        scan_root = args.snippet.parent
        paths = [args.snippet.name]
        repo_root = scan_root
    elif args.snippet_text:
        tmp = Path(tempfile.mkdtemp(prefix="rbl_snippet_"))
        ext = _ext_for_language(args.language)
        snippet_file = tmp / f"snippet{ext}"
        snippet_file.write_text(args.snippet_text)
        scan_root = tmp
        paths = [snippet_file.name]
        repo_root = scan_root
    elif args.pr:
        # iter-24 fix: scan the PR's CHANGED LINES, not the post-merge HEAD.
        # Approach: fetch the PR diff, parse it to learn which lines each
        # file added; fetch the HEAD content of each touched file; after the
        # scan, tag each finding with `in_diff` if its line falls in the
        # PR's added range.
        m = re.search(r"(?:/pull/|#)?(\d+)$", args.pr)
        if not m:
            raise SystemExit(f"could not parse PR number from {args.pr!r}")
        pr_num = m.group(1)
        tmp = Path(tempfile.mkdtemp(prefix="rbl_pr_"))

        # 1) fetch the PR diff (text) to learn added-line ranges per file
        diff_proc = subprocess.run(
            ["gh", "pr", "diff", pr_num, "--repo", args.repo],
            capture_output=True, text=True,
        )
        if diff_proc.returncode != 0:
            raise SystemExit(f"gh pr diff failed: {diff_proc.stderr}")
        diff_text = diff_proc.stdout
        # Parse `diff --git a/X b/Y` blocks; for each, extract `+N,M` hunk
        # headers — these are the added-line ranges in the NEW file.
        added_ranges: dict[str, list[tuple[int, int]]] = {}
        cur_file: str | None = None
        for ln in diff_text.splitlines():
            gm = re.match(r"^diff --git a/(\S+) b/(\S+)", ln)
            if gm:
                cur_file = gm.group(2)
                added_ranges.setdefault(cur_file, [])
                continue
            hm = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", ln)
            if hm and cur_file:
                start = int(hm.group(1))
                count = int(hm.group(2) or "1")
                if count > 0:
                    added_ranges[cur_file].append((start, start + count - 1))
        # 2) fetch HEAD content of each changed file
        proc = subprocess.run(
            ["gh", "pr", "view", pr_num, "--repo", args.repo,
             "--json", "files"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise SystemExit(f"gh pr view failed: {proc.stderr}")
        pr_meta = json.loads(proc.stdout)
        for f in pr_meta.get("files", []):
            path = f["path"]
            content_proc = subprocess.run(
                ["gh", "api", f"repos/{args.repo}/contents/{path}",
                 "--jq", ".content"],
                capture_output=True, text=True,
            )
            if content_proc.returncode != 0:
                continue
            import base64
            try:
                content = base64.b64decode(content_proc.stdout.strip()).decode(errors="replace")
            except Exception:
                continue
            dest = tmp / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
        scan_root = tmp
        paths = None
        repo_root = tmp
        # Stash for the post-scan tagging step
        pr_added_ranges = added_ranges

    scan_json = out_dir / "scan.json"
    print(f"[review] scanning {scan_root}...", file=sys.stderr)
    scan_data = run_scan(scan_root, scan_json, paths=paths)

    findings = scan_data.get("findings", [])

    # iter-24: tag findings as in-diff or pre-existing if we have PR ranges.
    in_diff_count = 0
    if pr_added_ranges is not None:
        for f in findings:
            ranges = pr_added_ranges.get(f["file"], [])
            in_diff = any(s <= f["line"] <= e for s, e in ranges)
            f["in_diff"] = in_diff
            if in_diff:
                in_diff_count += 1
        # Sort: in-diff findings first
        findings.sort(key=lambda x: (not x.get("in_diff"), x["file"], x["line"]))

    if pr_added_ranges is not None:
        print(
            f"[review] {len(findings)} candidate finding(s) "
            f"({in_diff_count} inside PR-changed lines)",
            file=sys.stderr,
        )
    else:
        print(f"[review] {len(findings)} candidate finding(s)", file=sys.stderr)

    bundle_paths = []
    for i, f in enumerate(findings, 1):
        bundle_paths.append(str(build_review_bundle(f, repo_root, i, bundles_dir)))

    # INDEX.md — overview for the LLM consumer
    summary = {
        "scanned_at": scan_data.get("scanned_at"),
        "scan_root": str(scan_root),
        "n_findings": len(findings),
        "by_rule": scan_data.get("summary", {}).get("by_rule", {}),
        "by_severity": scan_data.get("summary", {}).get("by_severity", {}),
        "bundles": bundle_paths,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    index = [f"# Review session — {scan_data.get('scanned_at', '')}\n"]
    index.append(f"Scanned: `{scan_root}`\n")
    if pr_added_ranges is not None:
        index.append(f"\n**Mode**: PR diff-aware (in-diff: {in_diff_count}, "
                     f"pre-existing: {len(findings) - in_diff_count})\n")
    if not findings:
        # iter-24: explicit empty-state UX so the LLM consumer can
        # distinguish "clean code" from "scan broken".
        index.append("\n## 0 findings\n")
        index.append("No known anti-patterns detected in the scanned input.")
        index.append("\nRules attempted (none fired):")
        for k in sorted(summary["by_rule"].keys()):
            index.append(f"- `{k}`")
        index.append("")
        index.append("This is the expected outcome for code that follows the patterns.")
    else:
        index.append(f"\n## {len(findings)} candidate findings\n")
        for k, v in summary["by_rule"].items():
            if v:
                index.append(f"- **{k}**: {v}")
        index.append("\n## Bundles to review (in order)\n")
        for p in bundle_paths:
            index.append(f"- `{Path(p).relative_to(out_dir)}`")
    (out_dir / "INDEX.md").write_text("\n".join(index))

    # iter-24: terse one-line summary on stdout, after the path, so callers see
    # the gist immediately.
    if not findings:
        print("[review] 0 findings — input is clean", file=sys.stderr)
    else:
        print(f"[review] wrote {len(bundle_paths)} bundle(s) to {out_dir}", file=sys.stderr)
    print(str(out_dir))  # stdout: the output dir path, for the skill to consume


if __name__ == "__main__":
    main()
