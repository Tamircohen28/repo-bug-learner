"""Stage 4b: Synthesize Opengrep (Semgrep-compatible) rules for non-Scala patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass

import yaml
from rich.console import Console

from ..config import Config
from ..types import CandidateRule, Cluster, OpengrepLanguage
from .base import ClaudeClient, extract_code_block

console = Console()

LANGUAGE_GUIDANCE: dict[str, str] = {
    "typescript": (
        "TypeScript/JavaScript: watch for loose equality, missing await, "
        "array.sort() without comparator, timezone-unsafe Date usage."
    ),
    "javascript": (
        "JavaScript: same patterns as TypeScript; prefer explicit comparators and async handling."
    ),
    "python": (
        "Python: focus on mutable default arguments, bare except, missing None checks, "
        "async/await misuse, and shadowed builtins."
    ),
    "go": (
        "Go: focus on ignored errors (_ = fn()), defer in loops, nil pointer patterns, "
        "and goroutine leaks from unbounded channel sends."
    ),
}

SYSTEM_PROMPT_TEMPLATE = """You are an expert at writing Opengrep (Semgrep-compatible) rules for catching bug patterns in code.

You will be given a cluster of recurring bugs from a codebase. Synthesize ONE Opengrep YAML rule that catches the common pattern.

PROJECT CONTEXT:
{project_context}

TARGET LANGUAGE GUIDANCE:
{language_guidance}

CRITICAL CONSTRAINTS:
1. The rule must be valid Opengrep YAML, runnable as `semgrep scan --config=rule.yaml`.
2. Use `pattern-either` if there are multiple manifestations. Use `pattern-not` aggressively for precision.
3. Include metadata with origin-bugs (Jira keys) and category (correctness | security | performance | reliability).
4. Severity: ERROR for definite bugs, WARNING for likely bugs, INFO for code smells.
5. The message field MUST give an actionable fix.
6. Target only languages where this pattern actually appears.

OUTPUT FORMAT — exactly these three sections in order:

<analysis>...</analysis>
<rule_id>hyphen-case-id</rule_id>
<rule>```yaml ... ```</rule>
<test_snippets>``` ... ```</test_snippets>

In metadata use:
  owner: {rules_owner}
  origin-bugs: [PROJ-XXXX]
"""


@dataclass
class _ParsedSynthesis:
    rule_id: str
    rule_yaml: str
    test_snippets: list[str]
    rationale: str


class OpengrepSynthesizer:
    def __init__(self, claude: ClaudeClient, config: Config) -> None:
        self.claude = claude
        self.config = config
        self.rules_owner = config.rules_owner

    def _system_prompt(self, dominant_language: str) -> str:
        guidance = LANGUAGE_GUIDANCE.get(
            dominant_language,
            "Match the dominant language of the examples; use Semgrep language ids.",
        )
        return SYSTEM_PROMPT_TEMPLATE.format(
            project_context=self.config.project_context,
            language_guidance=guidance,
            rules_owner=self.rules_owner,
        )

    async def synthesize(
        self,
        cluster: Cluster,
        dominant_language: OpengrepLanguage | None = None,
    ) -> CandidateRule | None:
        if dominant_language:
            entries = [e for e in cluster.entries if e.language == dominant_language]
        else:
            entries = [e for e in cluster.entries if e.language != "scala"]
        if len(entries) < 2:
            return None

        dom = dominant_language or entries[0].language
        user_prompt = self._build_prompt(cluster, entries)
        try:
            resp = await self.claude.strong(
                self._system_prompt(dom), user_prompt, max_tokens=4096
            )
        except Exception as e:
            console.log(f"[red]Cluster {cluster.cluster_id} opengrep synthesis failed: {e}[/red]")
            return None

        parsed = self._parse(resp.text)
        if not parsed:
            return None

        try:
            yaml.safe_load(parsed.rule_yaml)
        except yaml.YAMLError as e:
            console.log(f"[yellow]Cluster {cluster.cluster_id}: invalid YAML: {e}[/yellow]")
            return None

        return CandidateRule(
            rule_id=parsed.rule_id,
            cluster_id=cluster.cluster_id,
            origin_bug_keys=[e.bug_key for e in entries],
            target="opengrep",
            rule_source=parsed.rule_yaml,
            test_inputs=parsed.test_snippets,
            test_outputs=[],
            rationale=parsed.rationale,
        )

    def _build_prompt(self, cluster: Cluster, entries: list) -> str:
        examples = []
        for i, e in enumerate(entries[:5], 1):
            examples.append(
                f"### Example {i}: {e.bug_key}  (language: {e.language})\n"
                f"**Bug summary:** {e.bug_summary}\n\n"
                f"**Buggy code:**\n```\n{e.buggy_code}\n```\n\n"
                f"**Fix diff:**\n```diff\n{e.fix_diff[:1500]}\n```"
            )
        return (
            f"Cluster {cluster.cluster_id} contains {len(entries)} related bugs.\n\n"
            + "\n\n---\n\n".join(examples)
        )

    def _parse(self, text: str) -> _ParsedSynthesis | None:
        def section(tag: str) -> str | None:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
            return m.group(1).strip() if m else None

        rationale = section("analysis")
        rule_id_raw = section("rule_id")
        rule_block = section("rule")
        snippets_block = section("test_snippets")

        if not all([rationale, rule_id_raw, rule_block, snippets_block]):
            return None

        rule_id = re.sub(r"[^a-z0-9-]", "", rule_id_raw.lower().strip())
        snippets_text = extract_code_block(snippets_block)
        snippets = [s.strip() for s in snippets_text.split("// ---") if s.strip()]

        return _ParsedSynthesis(
            rule_id=rule_id,
            rule_yaml=extract_code_block(rule_block, "yaml"),
            test_snippets=snippets,
            rationale=rationale,
        )
