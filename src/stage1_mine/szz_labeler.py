"""Stage 1b: Label bug-inducing commits via SZZ algorithm.

Given a fixing commit, walk back through git blame on the changed lines to identify
the commit(s) that introduced the buggy code. Uses PyDriller for the heavy lifting.

Two implementations behind a strategy flag:
  - "ra-szz" (default) — Refactoring-Aware SZZ from PyDriller. Filters out
    refactorings and trivial changes that aren't true bug introductions.
  - "llm4szz" — Higher precision via LLM-based candidate filtering (ISSTA 2025).
    Slower and costs LLM calls but materially better F1. Stub here; implement
    with a Claude prompt that classifies each SZZ candidate as bug-introducing
    or not given the fix-commit context.

Output: BugInducingCommit objects, persisted as part of the corpus build (stage 2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydriller import Git, ModifiedFile
from rich.console import Console

from ..types import BugInducingCommit, CodeBlock, FixingCommit

console = Console()

SZZStrategy = Literal["ra-szz", "llm4szz"]


class SZZLabeler:
    """Maps fixing commits → bug-inducing commits via blame-based SZZ."""

    def __init__(
        self,
        repos_root: Path,
        strategy: SZZStrategy = "ra-szz",
    ) -> None:
        """
        repos_root: directory where service repos are cloned. Each service should be
        at repos_root / <service_name>.
        """
        self.repos_root = repos_root
        self.strategy = strategy

    def label(self, fix: FixingCommit, bug_summary: str = "") -> list[BugInducingCommit]:
        """For one fixing commit, return the bug-inducing commits."""
        repo_path = self.repos_root / fix.repo
        if not repo_path.exists():
            console.log(f"[red]Repo not cloned: {repo_path}[/red]")
            return []

        git = Git(str(repo_path))
        fix_sha = fix.merge_commit_sha or (fix.fix_commit_shas[0] if fix.fix_commit_shas else "")
        if not fix_sha:
            return []

        try:
            fix_commit = git.get_commit(fix_sha)
        except Exception as e:
            console.log(f"[yellow]Couldn't load commit {fix_sha[:8]}: {e}[/yellow]")
            return []

        candidates = self._ra_szz(git, fix_commit)

        if self.strategy == "llm4szz":
            candidates = self._llm_filter(candidates, fix, bug_summary)

        return [self._build_bug_inducing(c, fix) for c in candidates]

    def _ra_szz(self, git: Git, fix_commit) -> list[_Candidate]:
        """Refactoring-Aware SZZ. PyDriller's get_commits_last_modified_lines does most of the work."""
        candidates: list[_Candidate] = []

        # PyDriller annotates each modified file with the prior commits that touched
        # the deleted/modified lines. Those prior commits are SZZ candidates.
        bug_inducing_map = git.get_commits_last_modified_lines(fix_commit)
        # Returns: dict[file_path, set[commit_sha]]

        for file_path, prior_shas in bug_inducing_map.items():
            # Skip non-source files
            if not self._is_source_file(file_path):
                continue

            modified_file = self._find_modified_file(fix_commit, file_path)
            if not modified_file:
                continue

            for sha in prior_shas:
                # Filter trivial commits (whitespace-only, comment-only, file moves)
                try:
                    prior_commit = git.get_commit(sha)
                except Exception:
                    continue
                if self._is_trivial(prior_commit):
                    continue

                candidates.append(_Candidate(
                    sha=sha,
                    file_path=file_path,
                    modified_file=modified_file,
                    prior_commit=prior_commit,
                ))

        return candidates

    def _llm_filter(
        self,
        candidates: list[_Candidate],
        fix: FixingCommit,
        bug_summary: str,
    ) -> list[_Candidate]:
        """
        LLM4SZZ — for each SZZ candidate, ask the LLM whether this commit really
        introduced the bug, given the fix and bug summary.

        Stub: implement against the configured Claude API in stage4_synthesize.base
        following the same prompt pattern. Returning candidates as-is for now.
        """
        # TODO: implement with a Claude call that returns {"bug_introducing": bool, "confidence": float}
        return candidates

    def _build_bug_inducing(self, c: _Candidate, fix: FixingCommit) -> BugInducingCommit:
        # Extract the buggy code blocks (the lines that were deleted/modified by the fix,
        # as they existed in the bug-inducing commit)
        buggy_blocks: list[CodeBlock] = []
        for line in (c.modified_file.diff_parsed.get("deleted") or []):
            line_no, content = line                          # PyDriller returns (line_no, text)
            language = _infer_lang(c.file_path)
            buggy_blocks.append(CodeBlock(
                file_path=c.file_path,
                start_line=line_no,
                end_line=line_no,
                language=language,
                content=content,
            ))

        return BugInducingCommit(
            bug_key=fix.bug_key,
            repo=fix.repo,
            sha=c.sha,
            author=c.prior_commit.author.email or c.prior_commit.author.name,
            authored_at=c.prior_commit.author_date,
            files=[c.file_path],
            buggy_code_blocks=buggy_blocks,
            fix_diff=fix.diff,
            fix_commit_sha=fix.merge_commit_sha or "",
            szz_confidence=0.7 if self.strategy == "ra-szz" else 0.9,
        )

    @staticmethod
    def _is_source_file(path: str) -> bool:
        return path.endswith((
            ".scala", ".js", ".ts", ".jsx", ".tsx", ".java", ".py", ".go",
        ))

    @staticmethod
    def _find_modified_file(fix_commit, file_path: str) -> ModifiedFile | None:
        for mf in fix_commit.modified_files:
            if mf.new_path == file_path or mf.old_path == file_path:
                return mf
        return None

    @staticmethod
    def _is_trivial(commit) -> bool:
        """Filter out refactorings, formatting changes, comment-only changes."""
        # Heuristic: tiny commits in one file with mostly-blank lines are often noise
        # TODO: integrate RefactoringMiner output here for higher precision
        return (
            len(commit.modified_files) == 0
            or commit.insertions + commit.deletions < 2
        )


class _Candidate:
    __slots__ = ("file_path", "modified_file", "prior_commit", "sha")

    def __init__(self, sha, file_path, modified_file, prior_commit):
        self.sha = sha
        self.file_path = file_path
        self.modified_file = modified_file
        self.prior_commit = prior_commit


def _infer_lang(path: str) -> str:
    if path.endswith(".scala"):
        return "scala"
    if path.endswith((".js", ".jsx")):
        return "javascript"
    if path.endswith((".ts", ".tsx")):
        return "typescript"
    if path.endswith(".py"):
        return "python"
    if path.endswith(".go"):
        return "go"
    return "other"
