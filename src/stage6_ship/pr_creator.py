"""Stage 6: Ship validated rules as PRs to the rules repos.

For each rule that passed validation:
  1. Create a feature branch on the appropriate rules repo
  2. Add the rule source + test input/output files
  3. Update the rules manifest if one exists
  4. Open a PR with a body that includes:
     - Origin Jira keys
     - Cluster description
     - Validation stats (precision, recall, FP count)
     - The LLM's rationale for human reviewers
  5. Request review from the configured team

Human review is REQUIRED. We never auto-merge rules.
"""

from __future__ import annotations


from github import Github
from rich.console import Console

from ..config import Config
from ..types import CandidateRule, ValidationResult

console = Console()


class PRShipper:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.gh = Github(
            base_url=config["github"]["base_url"],
            login_or_token=config.github_token,
        )
        self.scalafix_repo_name = config["rules_repos"]["scalafix_repo"]
        self.opengrep_repo_name = config["rules_repos"]["opengrep_repo"]
        self.branch_prefix = config["rules_repos"]["branch_prefix"]
        self.review_team = config["rules_repos"]["review_team"]

    def ship_validated(
        self,
        candidates: list[CandidateRule],
        results: list[ValidationResult],
    ) -> list[str]:
        """Returns list of PR URLs opened."""
        result_by_id = {r.rule_id: r for r in results}
        shipped: list[str] = []
        for rule in candidates:
            result = result_by_id.get(rule.rule_id)
            if not result or not result.ship:
                continue
            try:
                pr_url = self._ship_one(rule, result)
                shipped.append(pr_url)
                console.log(f"[green]Shipped {rule.rule_id} → {pr_url}[/green]")
            except Exception as e:
                console.log(f"[red]Failed to ship {rule.rule_id}: {e}[/red]")
        return shipped

    def _ship_one(self, rule: CandidateRule, result: ValidationResult) -> str:
        repo_name = self.scalafix_repo_name if rule.target == "scalafix" else self.opengrep_repo_name
        repo = self.gh.get_repo(repo_name)

        # Branch off main
        main = repo.get_branch("main")
        branch_name = f"{self.branch_prefix}/{rule.rule_id}"
        try:
            repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=main.commit.sha)
        except Exception:
            pass    # branch may already exist from a prior run

        if rule.target == "scalafix":
            self._add_scalafix_files(repo, branch_name, rule)
        else:
            self._add_opengrep_files(repo, branch_name, rule)

        pr_body = self._build_pr_body(rule, result)
        pr = repo.create_pull(
            title=f"auto-rule: {rule.rule_id} ({len(rule.origin_bug_keys)} origin bugs)",
            body=pr_body,
            head=branch_name,
            base="main",
        )
        try:
            pr.add_to_assignees(self.review_team.split("/")[-1])
        except Exception:
            pass
        pr.add_to_labels("auto-generated", "needs-review")
        return pr.html_url

    def _add_scalafix_files(self, repo, branch: str, rule: CandidateRule) -> None:
        # Rule source
        class_name = _class_name(rule.rule_id)
        rule_path = f"rules/src/main/scala/fix/{class_name}.scala"
        self._upsert_file(repo, branch, rule_path, rule.rule_source,
                          f"Add Scalafix rule {rule.rule_id}")

        # Test scaffolding
        if rule.test_inputs:
            self._upsert_file(repo, branch,
                              f"rules/src/test/resources/input/fix/{class_name}.scala",
                              rule.test_inputs[0],
                              f"Add test input for {rule.rule_id}")
        if rule.test_outputs:
            self._upsert_file(repo, branch,
                              f"rules/src/test/resources/output/fix/{class_name}.scala",
                              rule.test_outputs[0],
                              f"Add expected test output for {rule.rule_id}")

    def _add_opengrep_files(self, repo, branch: str, rule: CandidateRule) -> None:
        # One YAML per rule, organized by category if metadata has it
        import yaml as yaml_lib
        doc = yaml_lib.safe_load(rule.rule_source)
        category = (doc.get("rules") or [{}])[0].get("metadata", {}).get("category", "uncategorized")
        rule_path = f"rules/{category}/{rule.rule_id}.yaml"
        self._upsert_file(repo, branch, rule_path, rule.rule_source,
                          f"Add Opengrep rule {rule.rule_id}")

    def _upsert_file(self, repo, branch: str, path: str, content: str, message: str) -> None:
        try:
            existing = repo.get_contents(path, ref=branch)
            repo.update_file(path, message, content, existing.sha, branch=branch)
        except Exception:
            repo.create_file(path, message, content, branch=branch)

    def _build_pr_body(self, rule: CandidateRule, result: ValidationResult) -> str:
        return f"""\
## Auto-synthesized rule: `{rule.rule_id}`

**Cluster:** {rule.cluster_id}
**Origin bugs ({len(rule.origin_bug_keys)}):** {", ".join(rule.origin_bug_keys)}

### Validation
| Metric | Value | Threshold |
|--------|-------|-----------|
| Precision | {result.precision:.2%} | {self.config["validation"]["min_precision"]:.2%} |
| Recall on cluster | {result.recall_in_cluster:.2%} | {self.config["validation"]["min_recall_in_cluster"]:.2%} |
| FPs on clean main | {result.false_positives_on_clean} | ≤ {int(self.config["validation"]["max_false_positive_rate_on_clean"] * 1000)} |

### Rationale (from synthesis LLM)
{rule.rationale}

---

**Reviewer checklist:**
- [ ] Rule message is actionable (tells dev how to fix, message is actionable for developers)
- [ ] No obvious false-positive patterns missed in `pattern-not`
- [ ] Severity level appropriate (ERROR vs WARNING)
- [ ] Rule has been spot-checked against 2-3 origin bugs manually

This PR was auto-generated by `repo-bug-learner`. Approve to ship; close to send to refinement queue.
"""


def _class_name(rule_id: str) -> str:
    return "".join(part.capitalize() for part in rule_id.split("_"))
