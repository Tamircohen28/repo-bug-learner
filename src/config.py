"""Config loading. Organization-specific values live in config.toml."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Config:
    raw: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> Config:
        with path.open("rb") as f:
            raw = tomllib.load(f)
        return cls(raw=raw)

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    @property
    def jira_auth(self) -> tuple[str, str]:
        return os.environ["JIRA_USER"], os.environ["JIRA_TOKEN"]

    @property
    def github_token(self) -> str:
        return os.environ["GITHUB_TOKEN"]

    @property
    def anthropic_key(self) -> str:
        return os.environ["ANTHROPIC_API_KEY"]

    @property
    def ticket_pattern(self) -> re.Pattern[str]:
        pattern = self.raw.get("jira", {}).get("ticket_pattern", r"[A-Z]+-\d+")
        return re.compile(rf"\b({pattern})\b", re.IGNORECASE)

    @property
    def project_context(self) -> str:
        return self.raw.get("synthesis", {}).get(
            "project_context",
            "A multi-language monorepo with recurring bug-fix patterns.",
        )

    @property
    def rules_owner(self) -> str:
        synthesis = self.raw.get("synthesis", {})
        if "rules_owner" in synthesis:
            return synthesis["rules_owner"]
        return self.raw.get("rules_repos", {}).get("owner", "platform")

    @property
    def github_org(self) -> str:
        return self.raw.get("github", {}).get("org", "your-org")

    def github_repos(self) -> list[tuple[str, str]]:
        gh = self.raw.get("github", {})
        entries = gh.get("repos") or gh.get("services") or []
        repos: list[tuple[str, str]] = []
        for entry in entries:
            if ":" in entry:
                name, branch = entry.split(":", 1)
            else:
                name, branch = entry, "main"
            repos.append((name, branch))
        return repos

    @property
    def default_repo_hint(self) -> str:
        repos = self.github_repos()
        return repos[0][0] if repos else "backend"
