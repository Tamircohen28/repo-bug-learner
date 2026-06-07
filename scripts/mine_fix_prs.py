#!/usr/bin/env python3
"""Mine fix PRs from a GitHub repo via gh CLI and emit a JSONL corpus.

Designed to scale to ~100k commits / ~10k PRs per repo with no LLM in the loop.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

console = Console()

FIX_TITLE_PATTERNS = [
    re.compile(r"^(fix|bugfix|hotfix)[\(\[:]", re.IGNORECASE),
    re.compile(r"\bfix:", re.IGNORECASE),
    re.compile(r"^\[.*\]\s*fix", re.IGNORECASE),
]
JIRA_KEY_RE = re.compile(r"SCHED-\d+", re.IGNORECASE)

LANG_BY_EXT = {
    ".scala": "scala",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
}
ALLOWED_EXTS = set(LANG_BY_EXT.keys())

TEST_PATTERNS = [
    re.compile(r"/tests?/"),
    re.compile(r"Test\.scala$"),
    re.compile(r"\.test\.(t|j)sx?$"),
    re.compile(r"\.spec\.(t|j)sx?$"),
    re.compile(r"IT\.scala$"),
]

MAX_FILE_DIFF_BYTES = 50 * 1024


def is_fix_title(title: str) -> bool:
    if JIRA_KEY_RE.search(title):
        return True
    for pat in FIX_TITLE_PATTERNS:
        if pat.search(title):
            return True
    return False


def extract_jira_labels(*texts: str) -> list[str]:
    found = []
    seen = set()
    for t in texts:
        if not t:
            continue
        for m in JIRA_KEY_RE.findall(t):
            up = m.upper()
            if up not in seen:
                seen.add(up)
                found.append(up)
    return found


def is_test_path(path: str) -> bool:
    return any(p.search(path) for p in TEST_PATTERNS)


def lang_for(path: str) -> str | None:
    for ext, lang in LANG_BY_EXT.items():
        if path.endswith(ext):
            return lang
    return None


def parse_unified_diff(diff_text: str) -> list[dict]:
    """Parse unified diff into [{path, body, removed_lines}, ...].

    `body` is the per-file diff text (without the `diff --git` header but
    including `@@` hunk headers). `removed_lines` collects every `-line`
    (excluding `---` markers), with the leading `-` stripped.
    """
    files: list[dict] = []
    cur: dict | None = None
    in_hunk = False

    lines = diff_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git "):
            if cur is not None:
                files.append(cur)
            cur = {"path": None, "body_lines": [], "removed_lines": []}
            in_hunk = False
            i += 1
            continue
        if cur is None:
            i += 1
            continue
        if line.startswith("+++ "):
            # `+++ b/path/to/file` or `+++ /dev/null`
            p = line[4:].strip()
            if p.startswith("b/"):
                p = p[2:]
            if p != "/dev/null":
                cur["path"] = p
            i += 1
            continue
        if line.startswith("--- "):
            # `--- a/path/to/file` — fall back to this if +++ was /dev/null
            if cur.get("path") is None:
                p = line[4:].strip()
                if p.startswith("a/"):
                    p = p[2:]
                if p != "/dev/null":
                    cur["path"] = p
            i += 1
            continue
        if line.startswith("@@"):
            in_hunk = True
            cur["body_lines"].append(line)
            i += 1
            continue
        if in_hunk:
            cur["body_lines"].append(line)
            if line.startswith("-") and not line.startswith("---"):
                cur["removed_lines"].append(line[1:])
        i += 1

    if cur is not None:
        files.append(cur)

    out = []
    for f in files:
        if not f.get("path"):
            continue
        out.append(
            {
                "path": f["path"],
                "body": "\n".join(f["body_lines"]),
                "removed": "\n".join(f["removed_lines"]),
            }
        )
    return out


def gh_run(args: list[str], timeout: int = 90) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:  # noqa: BLE001
        return 1, "", str(e)


def fetch_pr_list(repo: str, since: str, limit: int) -> list[dict]:
    args = [
        "gh", "pr", "list",
        "--repo", repo,
        "--state", "merged",
        "--search", f"merged:>={since}",
        "--json", "number,title,mergedAt,url,body",
        "--limit", str(limit),
    ]
    code, out, err = gh_run(args, timeout=180)
    if code != 0:
        console.print(f"[red]gh pr list failed:[/red] {err.strip()}")
        sys.exit(1)
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        console.print(f"[red]Could not decode gh pr list JSON: {e}[/red]")
        sys.exit(1)


def fetch_pr_diff(repo: str, number: int) -> str | None:
    code, out, err = gh_run(
        ["gh", "pr", "diff", str(number), "--repo", repo, "--patch"],
        timeout=120,
    )
    if code != 0 or not out.strip():
        return None
    return out


def make_bug_summary(title: str) -> str:
    # Use the PR title as the bug summary, trimmed.
    t = title.strip()
    if len(t) > 200:
        t = t[:197] + "..."
    return t


def load_existing_keys(path: Path) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    if not path.exists():
        return keys
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                keys.add((rec.get("bug_key", ""), rec.get("file_path", "")))
            except Exception:  # noqa: BLE001
                continue
    return keys


def build_records_for_pr(repo: str, pr: dict, diff_text: str) -> list[dict]:
    pr_number = pr["number"]
    title = pr.get("title", "") or ""
    body = pr.get("body", "") or ""
    jira_labels = extract_jira_labels(title, body)
    pr_body_excerpt = body.strip()
    if len(pr_body_excerpt) > 500:
        pr_body_excerpt = pr_body_excerpt[:500]

    records = []
    for f in parse_unified_diff(diff_text):
        path = f["path"]
        if not path:
            continue
        lang = lang_for(path)
        if lang is None:
            continue
        if is_test_path(path):
            continue
        buggy_code = f["removed"]
        if not buggy_code.strip():
            continue
        fix_diff = f["body"]
        if len(fix_diff.encode("utf-8", errors="ignore")) > MAX_FILE_DIFF_BYTES:
            continue
        records.append(
            {
                "bug_key": f"PR-{pr_number}",
                "repo": repo,
                "file_path": path,
                "language": lang,
                "buggy_code": buggy_code,
                "fix_diff": fix_diff,
                "bug_summary": make_bug_summary(title),
                "jira_labels": jira_labels,
                "szz_confidence": 1.0,
                "pr_url": pr.get("url", ""),
                "pr_body_excerpt": pr_body_excerpt,
            }
        )
    return records


def main() -> int:
    p = argparse.ArgumentParser(description="Mine fix PRs into a JSONL corpus.")
    p.add_argument("--repo", required=True)
    p.add_argument("--since", required=True, help="YYYY-MM-DD")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--output", required=True)
    p.add_argument("--append", action="store_true")
    p.add_argument("--workers", type=int, default=8)
    args = p.parse_args()

    t0 = time.time()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    console.print(
        f"[bold]Listing merged PRs[/bold] in {args.repo} since {args.since} (limit {args.limit})..."
    )
    prs = fetch_pr_list(args.repo, args.since, args.limit)
    scanned = len(prs)
    console.print(f"  fetched {scanned} merged PRs")

    fix_prs = [pr for pr in prs if is_fix_title(pr.get("title", "") or "")]
    matched = len(fix_prs)
    console.print(f"  {matched} match fix-pattern")

    existing_keys: set[tuple[str, str]] = set()
    mode = "w"
    if args.append:
        mode = "a"
        existing_keys = load_existing_keys(out_path)
        if existing_keys:
            console.print(
                f"  loaded {len(existing_keys)} existing (bug_key,file_path) keys"
            )

    lang_counter: Counter[str] = Counter()
    dir_counter: Counter[str] = Counter()
    entries_written = 0
    prs_with_entries = 0
    prs_diff_failed = 0

    out_f = out_path.open(mode)
    try:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Diffing fix PRs", total=matched)

            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                fut_to_pr = {
                    ex.submit(fetch_pr_diff, args.repo, pr["number"]): pr
                    for pr in fix_prs
                }
                for fut in as_completed(fut_to_pr):
                    pr = fut_to_pr[fut]
                    try:
                        diff_text = fut.result()
                    except Exception:  # noqa: BLE001
                        diff_text = None
                    if not diff_text:
                        prs_diff_failed += 1
                        progress.advance(task)
                        continue
                    records = build_records_for_pr(args.repo, pr, diff_text)
                    wrote_for_pr = 0
                    for rec in records:
                        key = (rec["bug_key"], rec["file_path"])
                        if key in existing_keys:
                            continue
                        existing_keys.add(key)
                        out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        entries_written += 1
                        wrote_for_pr += 1
                        lang_counter[rec["language"]] += 1
                        top_dir = rec["file_path"].split("/", 1)[0]
                        dir_counter[top_dir] += 1
                    if wrote_for_pr:
                        prs_with_entries += 1
                    progress.advance(task)
    finally:
        out_f.close()

    elapsed = time.time() - t0

    console.print()
    console.print("[bold green]Done.[/bold green]")
    console.print(f"  PRs scanned:               {scanned}")
    console.print(f"  PRs matched fix-pattern:   {matched}")
    console.print(f"  PRs with diff fetch fail:  {prs_diff_failed}")
    console.print(f"  PRs producing entries:     {prs_with_entries}")
    console.print(f"  Corpus entries written:    {entries_written}")
    console.print(f"  Output:                    {out_path}")
    console.print(f"  Runtime:                   {elapsed:.1f}s")

    if lang_counter:
        console.print("\n[bold]By language[/bold]")
        for lang, n in lang_counter.most_common():
            console.print(f"  {lang:12s} {n}")
    if dir_counter:
        console.print("\n[bold]Top directories[/bold]")
        for d, n in dir_counter.most_common(10):
            console.print(f"  {d:40s} {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
