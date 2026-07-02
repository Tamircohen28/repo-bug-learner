#!/usr/bin/env python3
"""High-throughput git-log-based corpus miner.

Replaces gh-CLI miner for full-history mining by reading directly from a local
clone via `git log` / `git show`. Parallelized with multiprocessing.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

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
PR_NUM_RE = re.compile(r"\(#(\d+)\)")

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
    found: list[str] = []
    seen: set[str] = set()
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
    return any(pat.search(path) for pat in TEST_PATTERNS)


def lang_of(path: str) -> str | None:
    for ext, lang in LANG_BY_EXT.items():
        if path.endswith(ext):
            return lang
    return None


def parse_log(repo_path: str, since: str, all_branches: bool = False) -> list[dict]:
    """Return list of {sha, subject, author, date, body} for non-merge commits.

    all_branches=True passes --all to git log, picking up commits on non-master
    branches and detached tags. ~2x more commits on scheduler.
    """
    fmt = "%H%x00%s%x00%an%x00%ad%x00%b%x1e"
    cmd = [
        "git", "-C", repo_path, "log",
        f"--since={since}",
        f"--pretty=format:{fmt}",
        "--date=iso-strict",
        "--no-merges",
    ]
    if all_branches:
        cmd.insert(4, "--all")
    out = subprocess.run(cmd, capture_output=True, text=True, check=True, errors="replace").stdout
    commits = []
    for raw in out.split("\x1e"):
        raw = raw.strip("\n")
        if not raw:
            continue
        parts = raw.split("\x00")
        if len(parts) < 5:
            continue
        sha, subject, author, date, body = parts[0], parts[1], parts[2], parts[3], parts[4]
        commits.append({
            "sha": sha,
            "subject": subject,
            "author": author,
            "date": date,
            "body": body,
        })
    return commits


def parse_show_diff(diff_text: str) -> list[tuple[str, str]]:
    """Parse `git show` output into [(file_path, file_diff), ...]."""
    files: list[tuple[str, str]] = []
    current_path: str | None = None
    current_lines: list[str] = []
    in_hunk = False

    def flush():
        nonlocal current_path, current_lines, in_hunk
        if current_path and current_lines:
            files.append((current_path, "\n".join(current_lines)))
        current_path = None
        current_lines = []
        in_hunk = False

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            flush()
            # diff --git a/<path> b/<path>
            m = re.match(r"diff --git a/(.+) b/(.+)$", line)
            if m:
                current_path = m.group(2)
            in_hunk = False
        elif line.startswith("@@"):
            in_hunk = True
            current_lines.append(line)
        elif in_hunk:
            current_lines.append(line)
        # ignore index/+++/--- preamble
    flush()
    return files


def extract_buggy_code(file_diff: str) -> str:
    """Removed lines (excluding ---/+++ headers)."""
    out = []
    for line in file_diff.splitlines():
        if line.startswith("---"):
            continue
        if line.startswith("-"):
            out.append(line[1:])
    return "\n".join(out)


_REPO_PATH_WORKER: str | None = None
_REPO_NAME_WORKER: str | None = None


def _init_worker(repo_path: str, repo_name: str) -> None:
    global _REPO_PATH_WORKER, _REPO_NAME_WORKER
    _REPO_PATH_WORKER = repo_path
    _REPO_NAME_WORKER = repo_name


def _process_commit(commit: dict) -> list[dict]:
    repo_path = _REPO_PATH_WORKER
    repo_name = _REPO_NAME_WORKER
    sha = commit["sha"]
    subject = commit["subject"]
    body = commit["body"]
    date = commit["date"]

    try:
        diff_text = subprocess.run(
            ["git", "-C", repo_path, "show", "--format=", "--no-color",
             "--unified=3", sha],
            capture_output=True, text=True, check=True, errors="replace",
        ).stdout
    except subprocess.CalledProcessError:
        return []

    files = parse_show_diff(diff_text)
    if not files:
        return []

    jira_labels = extract_jira_labels(subject, body)
    short = sha[:12]
    bug_key = f"commit-{short}"

    pr_url = ""
    m = PR_NUM_RE.search(subject)
    if m:
        pr_url = f"https://github.com/{repo_name}/pull/{m.group(1)}"

    body_excerpt = (body or "").strip()[:500]

    records: list[dict] = []
    for fpath, fdiff in files:
        if is_test_path(fpath):
            continue
        lang = lang_of(fpath)
        if not lang:
            continue
        if len(fdiff.encode("utf-8", errors="replace")) > MAX_FILE_DIFF_BYTES:
            fdiff = fdiff.encode("utf-8", errors="replace")[:MAX_FILE_DIFF_BYTES].decode("utf-8", errors="replace")
        buggy = extract_buggy_code(fdiff)
        if not buggy.strip():
            continue
        records.append({
            "bug_key": bug_key,
            "repo": repo_name,
            "file_path": fpath,
            "language": lang,
            "buggy_code": buggy,
            "fix_diff": fdiff,
            "bug_summary": subject,
            "jira_labels": jira_labels,
            "szz_confidence": 1.0,
            "pr_url": pr_url,
            "pr_body_excerpt": body_excerpt,
            "committed_at": date,
            "commit_sha": sha,
        })
    return records


def load_existing_max_date(output_path: Path) -> str | None:
    if not output_path.exists():
        return None
    max_date: str | None = None
    with output_path.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = rec.get("committed_at")
            if d and (max_date is None or d > max_date):
                max_date = d
    return max_date


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-path", required=True)
    ap.add_argument("--repo-name", required=True)
    ap.add_argument("--since", default="2020-01-01")
    ap.add_argument("--output", required=True)
    ap.add_argument("--incremental", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--all-branches", action="store_true",
                    help="Pass --all to git log; includes non-master branches and tags")
    args = ap.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    since = args.since
    append = False
    if args.incremental:
        max_date = load_existing_max_date(output_path)
        if max_date:
            since = max_date
            append = True
            console.print(f"[cyan]Incremental: scanning since {since}[/cyan]")

    t0 = time.time()
    console.print(f"[cyan]Reading git log from {args.repo_path} since {since}...[/cyan]")
    commits = parse_log(args.repo_path, since, all_branches=args.all_branches)
    console.print(f"[green]Scanned {len(commits):,} commits[/green]")

    fix_commits = [c for c in commits if is_fix_title(c["subject"])]
    console.print(f"[green]Matched {len(fix_commits):,} fix-pattern commits[/green]")

    records: list[dict] = []
    lang_counter: Counter = Counter()
    dir_counter: Counter = Counter()

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing commits", total=len(fix_commits))
        with Pool(processes=args.workers,
                  initializer=_init_worker,
                  initargs=(args.repo_path, args.repo_name)) as pool:
            for recs in pool.imap_unordered(_process_commit, fix_commits, chunksize=16):
                for r in recs:
                    records.append(r)
                    lang_counter[r["language"]] += 1
                    top = r["file_path"].split("/", 1)[0]
                    dir_counter[top] += 1
                progress.advance(task)

    mode = "a" if append else "w"
    with output_path.open(mode) as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    size = output_path.stat().st_size

    console.print()
    console.print("[bold green]=== Mining complete ===[/bold green]")
    console.print(f"Commits scanned:    {len(commits):,}")
    console.print(f"Fix-pattern matches: {len(fix_commits):,}")
    console.print(f"Corpus entries written: {len(records):,}")
    console.print(f"Output: {output_path} ({size/1024/1024:.2f} MB)")
    console.print(f"Runtime: {elapsed:.1f}s")
    console.print()
    console.print("[bold]By language:[/bold]")
    for lang, n in lang_counter.most_common():
        console.print(f"  {lang:12s} {n:,}")
    console.print()
    console.print("[bold]Top top-level dirs:[/bold]")
    for d, n in dir_counter.most_common(15):
        console.print(f"  {d:40s} {n:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
