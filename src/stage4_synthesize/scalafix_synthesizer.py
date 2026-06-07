"""Stage 4a: Synthesize Scalafix rules from clusters."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rich.console import Console

from ..config import Config
from ..types import CandidateRule, Cluster
from .base import ClaudeClient, extract_code_block

console = Console()

SYSTEM_PROMPT_TEMPLATE = """You are an expert Scala static analysis engineer specialized in Scalafix rule authoring for Scala 2.12.21.

Your job: given a cluster of historically recurring bugs from a codebase (each represented as: bug summary + buggy code + the fix diff), synthesize a Scalafix rule that would catch this pattern on future PRs.

PROJECT CONTEXT:
{project_context}

CRITICAL CONSTRAINTS:
1. The codebase is Scala 2.12.21. Do not use Scala 3 syntax (no `given`/`using`, no `enum`, no top-level definitions, no `then` blocks).
2. Prefer SemanticRule over SyntacticRule when type information would improve precision.
3. Every rule must have a `Diagnostic` with severity, position, and a message that tells the developer how to fix it.
4. Output a rule that compiles. Do not invent Scalafix APIs. Use only scalafix.v1._ and scala.meta._ APIs.
5. Avoid overfitting to one example. The rule should generalize across the cluster.

OUTPUT FORMAT — exactly these four sections, in order:

<analysis>...</analysis>
<rule_id>snake_case_identifier</rule_id>
<rule_source>```scala ... ```</rule_source>
<test_input>```scala ... ```</test_input>
<test_expected_output>```scala ... ```</test_expected_output>
"""


@dataclass
class _ParsedSynthesis:
    rule_id: str
    rule_source: str
    test_input: str
    test_output: str
    rationale: str


class ScalafixSynthesizer:
    def __init__(self, claude: ClaudeClient, config: Config) -> None:
        self.claude = claude
        self.system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            project_context=config.project_context,
        )

    async def synthesize(self, cluster: Cluster) -> CandidateRule | None:
        scala_entries = [e for e in cluster.entries if e.language == "scala"]
        if len(scala_entries) < 2:
            return None

        user_prompt = self._build_prompt(cluster, scala_entries)
        console.log(
            f"Synthesizing Scalafix rule for cluster {cluster.cluster_id} "
            f"({len(scala_entries)} entries)"
        )

        try:
            resp = await self.claude.strong(self.system_prompt, user_prompt, max_tokens=6144)
        except Exception as e:
            console.log(f"[red]Cluster {cluster.cluster_id} synthesis failed: {e}[/red]")
            return None

        parsed = self._parse(resp.text)
        if not parsed:
            console.log(f"[yellow]Cluster {cluster.cluster_id}: couldn't parse LLM response[/yellow]")
            return None

        return CandidateRule(
            rule_id=parsed.rule_id,
            cluster_id=cluster.cluster_id,
            origin_bug_keys=[e.bug_key for e in scala_entries],
            target="scalafix",
            rule_source=parsed.rule_source,
            test_inputs=[parsed.test_input],
            test_outputs=[parsed.test_output],
            rationale=parsed.rationale,
        )

    def _build_prompt(self, cluster: Cluster, entries: list) -> str:
        examples = []
        for i, e in enumerate(entries[:5], 1):
            examples.append(
                f"### Example {i}: {e.bug_key}\n"
                f"**Bug summary:** {e.bug_summary}\n\n"
                f"**Buggy code:**\n```scala\n{e.buggy_code}\n```\n\n"
                f"**Fix diff (first 1500 chars):**\n```diff\n{e.fix_diff[:1500]}\n```"
            )

        return (
            f"Cluster {cluster.cluster_id} contains {len(entries)} bugs that look related.\n"
            f"Cluster description (if any): {cluster.description or '(none yet)'}\n\n"
            "Synthesize ONE Scalafix rule that catches the common pattern.\n\n"
            + "\n\n---\n\n".join(examples)
        )

    def _parse(self, text: str) -> _ParsedSynthesis | None:
        def section(tag: str) -> str | None:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
            return m.group(1).strip() if m else None

        rationale = section("analysis")
        rule_id_raw = section("rule_id")
        rule_block = section("rule_source")
        input_block = section("test_input")
        output_block = section("test_expected_output")

        if not all([rationale, rule_id_raw, rule_block, input_block, output_block]):
            return None

        rule_id = re.sub(r"[^a-z0-9_]", "", rule_id_raw.lower().strip())
        return _ParsedSynthesis(
            rule_id=rule_id,
            rule_source=extract_code_block(rule_block, "scala"),
            test_input=extract_code_block(input_block, "scala"),
            test_output=extract_code_block(output_block, "scala"),
            rationale=rationale,
        )
