"""Shared Claude client. Uses configurable base_url (Anthropic API or compatible proxy).

Two model tiers:
  - strong (Opus 4.8): rule synthesis with adaptive thinking, xhigh effort, and streaming
  - fast (Haiku 4.5): bulk tasks like SZZ candidate filtering

Concurrency is bounded via asyncio.Semaphore to respect API rate limits.
The SDK handles 429/5xx retries automatically (max_retries=3). Tenacity covers
network-level failures (connection errors, timeouts) only.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from anthropic import APIConnectionError, APITimeoutError, AsyncAnthropic
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
            max_retries=3,  # SDK auto-retries 429 and 5xx
        )
        self._semaphore = asyncio.Semaphore(int(config["claude"]["max_concurrent_calls"]))
        self.model_strong = config["claude"]["model_strong"]
        self.model_fast = config["claude"]["model_fast"]

    async def strong(self, system: str, user: str, max_tokens: int = 4096) -> ClaudeResponse:
        """Opus call with adaptive thinking, xhigh effort, prompt caching, and streaming.

        Streaming avoids SDK HTTP timeouts on large outputs. Adaptive thinking lets
        the model decide when deep reasoning is worth the token cost. xhigh effort
        is the recommended setting for coding/synthesis tasks on Opus 5.
        cache_control on the system prompt is a no-op for short prompts but kicks in
        automatically when the project_context grows large enough (≥4096 tokens).
        """
        return await self._call_strong(system, user, max_tokens)

    async def fast(self, system: str, user: str, max_tokens: int = 1024) -> ClaudeResponse:
        """Haiku call — no thinking, no effort (unsupported on Haiku 4.5)."""
        return await self._call(self.model_fast, system, user, max_tokens)

    @retry(
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, max=30),
    )
    async def _call_strong(self, system: str, user: str, max_tokens: int) -> ClaudeResponse:
        async with self._semaphore, self._client.messages.stream(
            model=self.model_strong,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            output_config={"effort": "xhigh"},
            messages=[{"role": "user", "content": user}],
        ) as stream:
            final = await stream.get_final_message()

        text = "".join(block.text for block in final.content if block.type == "text")
        usage = final.usage
        return ClaudeResponse(
            text=text,
            usage={
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
                "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            },
        )

    @retry(
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError)),
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
        text = "".join(block.text for block in resp.content if block.type == "text")
        return ClaudeResponse(
            text=text,
            usage={
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            },
        )


def extract_code_block(text: str, language: str | None = None) -> str:
    """Pull the first fenced code block from an LLM response, optionally filtering by language."""
    pattern = rf"```{language}\s*\n(.*?)\n```" if language else r"```(?:\w+)?\s*\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()
