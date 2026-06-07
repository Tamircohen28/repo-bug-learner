"""Shared Claude client. Uses configurable base_url (Anthropic API or compatible proxy).

Two model tiers:
  - strong (Opus): rule synthesis, cluster summarization, validation reasoning
  - fast (Haiku): bulk tasks like SZZ candidate filtering

Concurrency is bounded via asyncio.Semaphore to respect API rate limits.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic
from rich.console import Console
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import Config

console = Console()


@dataclass
class ClaudeResponse:
    text: str
    usage: dict[str, int]


class ClaudeClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._client = AsyncAnthropic(
            api_key=config.anthropic_key,
            base_url=config["claude"]["base_url"],
        )
        self._semaphore = asyncio.Semaphore(int(config["claude"]["max_concurrent_calls"]))
        self.model_strong = config["claude"]["model_strong"]
        self.model_fast = config["claude"]["model_fast"]

    async def strong(self, system: str, user: str, max_tokens: int = 4096) -> ClaudeResponse:
        return await self._call(self.model_strong, system, user, max_tokens)

    async def fast(self, system: str, user: str, max_tokens: int = 1024) -> ClaudeResponse:
        return await self._call(self.model_fast, system, user, max_tokens)

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, max=30),
    )
    async def _call(self, model: str, system: str, user: str, max_tokens: int) -> ClaudeResponse:
        async with self._semaphore:
            resp = await self._client.messages.create(
                model=model,
                system=system,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": user}],
            )
        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        return ClaudeResponse(
            text=text,
            usage={
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            },
        )


def extract_code_block(text: str, language: str | None = None) -> str:
    """Pull the first fenced code block from an LLM response, optionally filtering by language."""
    import re
    if language:
        pattern = rf"```{language}\s*\n(.*?)\n```"
    else:
        pattern = r"```(?:\w+)?\s*\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()
