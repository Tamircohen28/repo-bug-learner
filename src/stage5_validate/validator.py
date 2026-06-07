"""Stage 5: Validate candidate rules against the historical corpus.

A candidate rule must clear three bars to ship:
  1. Recall on its own cluster ≥ min_recall_in_cluster (default 0.50)
       — the rule should catch at least half of the bugs it was synthesized from
  2. Precision on the full corpus ≥ min_precision (default 0.85)
       — of all bugs the rule flags, at least 85% should actually be in its cluster
       (or a closely-related one — we treat off-cluster flags as false positives)
  3. False positive rate on current clean code ≤ max_fp_rate (default 0.02)
       — run the rule against latest main of the service; if it lights up >2% of
       files, it's too noisy regardless of recall

Below thresholds → mark `ship=False`. The rule goes to the human-review queue
with the failure reason, not to the auto-PR pipeline.

Both Scalafix and Opengrep validation work the same way: we have a small driver
shell that runs the tool against test inputs and parses results.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console

from ..config import Config
from ..types import CandidateRule, CorpusEntry, ValidationResult

console = Console()


class Validator:
    """Dispatches to Scalafix or Opengrep validator based on rule target."""

    def __init__(self, config: Config, corpus: list[CorpusEntry], scala_repos_root: Path) -> None:
        self.config = config
        self.corpus = corpus
        self.scala_repos_root = scala_repos_root
        v = config["validation"]
        self.min_precision = float(v["min_precision"])
        self.min_recall = float(v["min_recall_in_cluster"])
        self.max_fp_rate = float(v["max_false_positive_rate_on_clean"])

    async def validate(self, rule: CandidateRule) -> ValidationResult:
        if rule.target == "scalafix":
            return await self._validate_scalafix(rule)
        if rule.target == "opengrep":
            return await self._validate_opengrep(rule)
        return ValidationResult(rule_id=rule.rule_id, precision=0, recall_in_cluster=0,
                                false_positives_on_clean=0, error="unknown target")

    # -- Scalafix --------------------------------------------------------

    async def _validate_scalafix(self, rule: CandidateRule) -> ValidationResult:
        """
        1. Compile the rule with scalafix-testkit.
        2. Run it against test_inputs to confirm it matches expected outputs.
        3. Sample 10-20 corpus entries from other clusters; ensure rule doesn't
           flag them (precision check).
        4. Run it against latest main of the service; count false positives.
        """
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            ok, error = self._compile_scalafix_rule(rule, workdir)
            if not ok:
                return ValidationResult(rule_id=rule.rule_id, precision=0, recall_in_cluster=0,
                                        false_positives_on_clean=0, error=error)

            # In-cluster recall: testkit's input.scala IS the cluster representative
            recall = self._run_scalafix_testkit(rule, workdir)

            # Out-of-cluster precision: sample entries from other clusters, ensure they don't match
            other_entries = [e for e in self.corpus if e.cluster_id != rule.cluster_id and e.language == "scala"]
            fp_count = self._count_scalafix_matches_in_snippets(rule, workdir, other_entries[:20])
            precision = 1.0 - (fp_count / max(20, 1))

            # Clean-code false positives: scan latest main of the service.
            clean_fp = self._scan_clean_main_scalafix(rule, workdir)

        ship = (
            precision >= self.min_precision
            and recall >= self.min_recall
            and clean_fp <= int(self.max_fp_rate * 1000)        # rough: ≤2% of ~1000 files
        )
        return ValidationResult(
            rule_id=rule.rule_id,
            precision=precision,
            recall_in_cluster=recall,
            false_positives_on_clean=clean_fp,
            ship=ship,
        )

    def _compile_scalafix_rule(self, rule: CandidateRule, workdir: Path) -> tuple[bool, str | None]:
        """Drop the rule into a stub scalafix-testkit project and try to compile."""
        # Stub: a real implementation would `sbt new scalacenter/scalafix.g8` once and
        # then `cp` the generated rule into rules/src/main/scala/fix/.
        # For now we shell out to sbt assuming a pre-prepared template exists at
        # rules-repo-templates/scalafix-rules-template.
        template_root = Path(__file__).parents[2] / "rules-repo-templates" / "scalafix-rules-template"
        rule_file = workdir / "rules" / "src" / "main" / "scala" / "fix" / f"{rule.rule_id}.scala"
        rule_file.parent.mkdir(parents=True, exist_ok=True)
        rule_file.write_text(rule.rule_source)

        result = subprocess.run(
            ["sbt", "rules/compile"],
            cwd=template_root,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            return False, f"sbt compile failed:\n{result.stderr[-1500:]}"
        return True, None

    def _run_scalafix_testkit(self, rule: CandidateRule, workdir: Path) -> float:
        """Use scalafix-testkit to verify the rule fires on its own input.scala."""
        # Write input and expected output into the testkit resource dirs
        # Then run `sbt tests/test` for that specific rule
        # Return 1.0 if test passes (rule fires correctly on the cluster representative), else 0.0
        template_root = Path(__file__).parents[2] / "rules-repo-templates" / "scalafix-rules-template"
        input_path = template_root / "rules" / "src" / "test" / "resources" / "input" / "fix" / f"{rule.rule_id}.scala"
        output_path = template_root / "rules" / "src" / "test" / "resources" / "output" / "fix" / f"{rule.rule_id}.scala"

        if not rule.test_inputs or not rule.test_outputs:
            return 0.0
        input_path.write_text(rule.test_inputs[0])
        output_path.write_text(rule.test_outputs[0])

        result = subprocess.run(
            ["sbt", f"tests/testOnly fix.{_class_name(rule.rule_id)}Test"],
            cwd=template_root,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return 1.0 if result.returncode == 0 else 0.0

    def _count_scalafix_matches_in_snippets(
        self, rule: CandidateRule, workdir: Path, entries: list[CorpusEntry]
    ) -> int:
        """Run the rule against each snippet, count how many it flags."""
        matches = 0
        template_root = Path(__file__).parents[2] / "rules-repo-templates" / "scalafix-rules-template"
        for entry in entries:
            snippet_path = workdir / "snippet.scala"
            snippet_path.write_text(entry.buggy_code)
            result = subprocess.run(
                ["scalafix", "--rules", rule.rule_id, "--check", str(snippet_path)],
                cwd=template_root, capture_output=True, text=True, timeout=30,
            )
            # Scalafix exits non-zero when a rule fires and --check is set
            if result.returncode != 0:
                matches += 1
        return matches

    def _scan_clean_main_scalafix(self, rule: CandidateRule, workdir: Path) -> int:
        """Scan latest main of the service, count files where the rule fires.

        Stub for the demo: a real run clones/updates the repo, runs sbt scalafix
        with the new rule against the main branch, and counts violations.
        """
        # TODO: implement once you wire up the service-repo path resolution
        return 0

    # -- Opengrep ---------------------------------------------------------

    async def _validate_opengrep(self, rule: CandidateRule) -> ValidationResult:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            rule_path = workdir / f"{rule.rule_id}.yaml"
            rule_path.write_text(rule.rule_source)

            # Recall: run the rule against each test snippet. Each should match.
            matched_test = 0
            for snippet in rule.test_inputs:
                snippet_path = workdir / f"test_{matched_test}.{_ext_for_rule(rule)}"
                snippet_path.write_text(snippet)
                if self._opengrep_matches(rule_path, snippet_path):
                    matched_test += 1
            recall = matched_test / max(len(rule.test_inputs), 1)

            # Precision: sample 20 entries from other clusters; opengrep should NOT fire
            other_entries = [
                e for e in self.corpus
                if e.cluster_id != rule.cluster_id
                and (e.language in _opengrep_langs(rule))
            ][:20]
            fps = 0
            for entry in other_entries:
                snippet_path = workdir / f"other_{entry.bug_key}.{_ext_for_lang(entry.language)}"
                snippet_path.write_text(entry.buggy_code)
                if self._opengrep_matches(rule_path, snippet_path):
                    fps += 1
            precision = 1.0 - (fps / max(len(other_entries), 1))

        ship = precision >= self.min_precision and recall >= self.min_recall
        return ValidationResult(
            rule_id=rule.rule_id,
            precision=precision,
            recall_in_cluster=recall,
            false_positives_on_clean=0,           # populate when wiring clean-main scan
            ship=ship,
        )

    @staticmethod
    def _opengrep_matches(rule_path: Path, target: Path) -> bool:
        result = subprocess.run(
            ["opengrep", "scan", "--config", str(rule_path), "--json", str(target)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode not in (0, 1):     # 1 = findings present, fine for our purposes
            return False
        try:
            data = json.loads(result.stdout)
            return bool(data.get("results"))
        except json.JSONDecodeError:
            return False


def _class_name(rule_id: str) -> str:
    return "".join(part.capitalize() for part in rule_id.split("_"))


def _ext_for_lang(lang: str) -> str:
    return {"scala": "scala", "javascript": "js", "typescript": "ts"}.get(lang, "txt")


def _ext_for_rule(rule: CandidateRule) -> str:
    yaml_doc = next(iter(__import__("yaml").safe_load(rule.rule_source).get("rules", [])), {})
    langs = yaml_doc.get("languages") or ["txt"]
    return _ext_for_lang(langs[0])


def _opengrep_langs(rule: CandidateRule) -> set[str]:
    import yaml
    yaml_doc = next(iter(yaml.safe_load(rule.rule_source).get("rules", [])), {})
    return set(yaml_doc.get("languages") or [])
