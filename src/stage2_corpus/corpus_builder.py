"""Stage 2: Assemble the training corpus.

Joins the outputs of stage 1 (Jira bugs, fixing commits, SZZ-labeled bug-inducing
commits) into the canonical CorpusEntry format consumed by stages 3-5.

Each row contains the minimum context an LLM needs to synthesize a rule:
  - the buggy code (as it existed before the fix)
  - the fix diff
  - the bug summary (semantic intent of the bug)
  - jira labels (for grouping / filtering)

Output: out/corpus/corpus.jsonl
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from rich.console import Console

from ..types import BugInducingCommit, CorpusEntry, FixingCommit, JiraBug

console = Console()


class CorpusBuilder:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def build(
        self,
        bugs: list[JiraBug],
        fixing_commits: list[FixingCommit],
        bug_inducing: list[BugInducingCommit],
    ) -> list[CorpusEntry]:
        bug_by_key = {b.key: b for b in bugs}
        fix_by_key = {fc.bug_key: fc for fc in fixing_commits}     # one fix per bug; if multiple, keep largest

        entries: list[CorpusEntry] = []
        for bi in bug_inducing:
            bug = bug_by_key.get(bi.bug_key)
            fix = fix_by_key.get(bi.bug_key)
            if not bug or not fix:
                continue

            for block in bi.buggy_code_blocks:
                if not block.content.strip():
                    continue
                entries.append(CorpusEntry(
                    bug_key=bi.bug_key,
                    repo=bi.repo,
                    file_path=block.file_path,
                    language=block.language,
                    buggy_code=block.content,
                    fix_diff=fix.diff,
                    bug_summary=bug.summary,
                    jira_labels=bug.labels,
                    szz_confidence=bi.szz_confidence,
                ))

        console.log(f"Built corpus with {len(entries)} entries from {len(bug_inducing)} bug-inducing commits")
        return entries

    def persist(self, entries: list[CorpusEntry]) -> Path:
        corpus_dir = self.output_dir / "corpus"
        corpus_dir.mkdir(parents=True, exist_ok=True)
        out_path = corpus_dir / "corpus.jsonl"
        with out_path.open("w") as f:
            for e in entries:
                f.write(json.dumps(asdict(e)) + "\n")
        console.log(f"Wrote {out_path}")
        return out_path

    @staticmethod
    def load(path: Path) -> list[CorpusEntry]:
        entries: list[CorpusEntry] = []
        with path.open() as f:
            for line in f:
                d = json.loads(line)
                entries.append(CorpusEntry(**d))
        return entries
