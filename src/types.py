"""Shared data types used across all pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

Language = Literal["scala", "javascript", "typescript", "python", "go", "node", "other"]
OpengrepLanguage = Literal["typescript", "javascript", "python", "go"]


@dataclass
class JiraBug:
    """A closed bug fetched from Jira."""

    key: str
    summary: str
    description: str
    resolved_at: datetime
    labels: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    severity: str | None = None


@dataclass
class FixingCommit:
    """A commit that fixes a JiraBug, linked via PR."""

    bug_key: str
    repo: str
    pr_number: int
    pr_url: str
    merge_commit_sha: str
    fix_commit_shas: list[str]
    diff: str
    changed_files: list[str]
    lines_added: int
    lines_removed: int


@dataclass
class BugInducingCommit:
    """A commit identified by SZZ as having introduced a JiraBug."""

    bug_key: str
    repo: str
    sha: str
    author: str
    authored_at: datetime
    files: list[str]
    buggy_code_blocks: list[CodeBlock]
    fix_diff: str
    fix_commit_sha: str
    szz_confidence: float


@dataclass
class CodeBlock:
    """A region of code identified as buggy."""

    file_path: str
    start_line: int
    end_line: int
    language: Language
    content: str


@dataclass
class CorpusEntry:
    """One row in the corpus JSONL: a buggy code block + its fix + context."""

    bug_key: str
    repo: str
    file_path: str
    language: str
    buggy_code: str
    fix_diff: str
    bug_summary: str
    jira_labels: list[str]
    szz_confidence: float
    embedding: list[float] | None = None
    cluster_id: int | None = None


@dataclass
class Cluster:
    """A group of corpus entries representing the same recurring pattern."""

    cluster_id: int
    entries: list[CorpusEntry]
    centroid_embedding: list[float]
    description: str | None = None


@dataclass
class CandidateRule:
    """A rule synthesized by the LLM, not yet validated."""

    rule_id: str
    cluster_id: int
    origin_bug_keys: list[str]
    target: Literal["scalafix", "opengrep"]
    rule_source: str
    test_inputs: list[str]
    test_outputs: list[str]
    rationale: str


@dataclass
class ValidationResult:
    """Outcome of running a CandidateRule against the corpus."""

    rule_id: str
    precision: float
    recall_in_cluster: float
    false_positives_on_clean: int
    error: str | None = None
    ship: bool = False


@dataclass
class PipelineState:
    """Carried through the orchestrator. LangGraph-shaped."""

    config_path: Path
    repo: str
    since: datetime
    output_dir: Path
    bugs: list[JiraBug] = field(default_factory=list)
    fixing_commits: list[FixingCommit] = field(default_factory=list)
    bug_inducing_commits: list[BugInducingCommit] = field(default_factory=list)
    corpus: list[CorpusEntry] = field(default_factory=list)
    clusters: list[Cluster] = field(default_factory=list)
    candidate_rules: list[CandidateRule] = field(default_factory=list)
    validated_rules: list[ValidationResult] = field(default_factory=list)
