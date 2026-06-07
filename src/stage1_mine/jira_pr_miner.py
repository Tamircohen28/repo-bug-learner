"""Stage 1a: Mine Jira bugs and their linked fixing PRs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from github import Github
from jira import JIRA
from rich.console import Console
from rich.progress import track
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Config
from ..types import FixingCommit, JiraBug

console = Console()


class JiraPRMiner:
    def __init__(self, config: Config) -> None:
        self.config = config
        user, token = config.jira_auth
        self.jira = JIRA(server=config["jira"]["url"], basic_auth=(user, token))
        self.gh = Github(
            base_url=config["github"]["base_url"],
            login_or_token=config.github_token,
        )
        self.org = config.github_org
        self.repos = config.github_repos()
        self.ticket_re = config.ticket_pattern

    def mine(self, since: datetime) -> list[tuple[JiraBug, list[FixingCommit]]]:
        """Returns list of (bug, [fixing_commits]) pairs."""
        bugs = self._fetch_jira_bugs(since)
        console.log(f"Fetched {len(bugs)} closed bugs from Jira")

        results: list[tuple[JiraBug, list[FixingCommit]]] = []
        for bug in track(bugs, description="Linking PRs"):
            commits = self._find_fixing_commits(bug)
            if commits:
                results.append((bug, commits))

        with_prs_pct = len(results) / max(len(bugs), 1) * 100
        console.log(f"Linked PRs found for {len(results)}/{len(bugs)} bugs ({with_prs_pct:.1f}%)")
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def _fetch_jira_bugs(self, since: datetime) -> list[JiraBug]:
        jql = self.config["jira"]["jql_template"].format(
            project=self.config["jira"]["project_key"],
            since=since.strftime("%Y-%m-%d"),
        )
        max_results = self.config["jira"].get("max_bugs", 500)

        issues = self.jira.search_issues(jql, maxResults=max_results, expand="changelog")
        bugs: list[JiraBug] = []
        for issue in issues:
            try:
                bugs.append(JiraBug(
                    key=issue.key,
                    summary=issue.fields.summary or "",
                    description=issue.fields.description or "",
                    resolved_at=datetime.fromisoformat(
                        issue.fields.resolutiondate.replace("Z", "+00:00")
                    ),
                    labels=list(issue.fields.labels or []),
                    components=[c.name for c in (issue.fields.components or [])],
                    severity=getattr(issue.fields, "priority", None) and issue.fields.priority.name,
                ))
            except Exception as e:
                console.log(f"[yellow]Skipped {issue.key}: {e}[/yellow]")
        return bugs

    def _find_fixing_commits(self, bug: JiraBug) -> list[FixingCommit]:
        commits = self._find_via_jira_remote_links(bug)
        if commits:
            return commits
        return self._find_via_github_search(bug)

    def _find_via_jira_remote_links(self, bug: JiraBug) -> list[FixingCommit]:
        try:
            remote_links = self.jira.remote_links(bug.key)
        except Exception:
            return []

        commits: list[FixingCommit] = []
        for link in remote_links:
            url = link.object.url
            if "/pull/" not in url:
                continue
            commit = self._fetch_pr_as_fixing_commit(bug.key, url)
            if commit:
                commits.append(commit)
        return commits

    def _find_via_github_search(self, bug: JiraBug) -> list[FixingCommit]:
        commits: list[FixingCommit] = []
        for repo_name, _branch in self.repos:
            try:
                query = f"repo:{self.org}/{repo_name} is:pr is:merged {bug.key} in:title,body"
                results = self.gh.search_issues(query=query)
                for issue in results[:5]:
                    pr_url = issue.html_url
                    if "/pull/" not in pr_url:
                        continue
                    commit = self._fetch_pr_as_fixing_commit(bug.key, pr_url)
                    if commit:
                        commits.append(commit)
            except Exception as e:
                console.log(f"[yellow]GitHub search failed for {bug.key} in {repo_name}: {e}[/yellow]")
        return commits

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def _fetch_pr_as_fixing_commit(self, bug_key: str, pr_url: str) -> FixingCommit | None:
        match = re.search(r"/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
        if not match:
            return None
        org, repo_name, pr_number = match.group(1), match.group(2), int(match.group(3))

        repo = self.gh.get_repo(f"{org}/{repo_name}")
        pr = repo.get_pull(pr_number)
        if not pr.merged:
            return None

        body = (pr.title or "") + " " + (pr.body or "")
        if bug_key not in body and not any(
            bug_key in c.commit.message for c in pr.get_commits()
        ):
            if not self.ticket_re.search(body):
                return None

        fix_shas = [c.sha for c in pr.get_commits()]
        diff = self._fetch_pr_diff(repo, pr_number)
        return FixingCommit(
            bug_key=bug_key,
            repo=repo_name,
            pr_number=pr_number,
            pr_url=pr_url,
            merge_commit_sha=pr.merge_commit_sha or "",
            fix_commit_shas=fix_shas,
            diff=diff,
            changed_files=[f.filename for f in pr.get_files()],
            lines_added=pr.additions,
            lines_removed=pr.deletions,
        )

    def _fetch_pr_diff(self, repo, pr_number: int) -> str:
        url = f"{repo.url}/pulls/{pr_number}"
        headers = {"Accept": "application/vnd.github.v3.diff"}
        _, data = repo._requester.requestBlobAndCheck("GET", url, headers=headers)
        return data if isinstance(data, str) else data.decode("utf-8", errors="replace")


def persist_raw(
    pairs: list[tuple[JiraBug, list[FixingCommit]]],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "bugs.jsonl"
    with out_path.open("w") as f:
        for bug, commits in pairs:
            row = {
                "bug": _to_jsonable(asdict(bug)),
                "fixing_commits": [_to_jsonable(asdict(c)) for c in commits],
            }
            f.write(json.dumps(row) + "\n")
    console.log(f"Wrote {len(pairs)} rows to {out_path}")
    return out_path


def _to_jsonable(d: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()}
