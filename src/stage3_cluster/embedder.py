"""Stage 3a: Embed corpus entries for clustering.

Two backends:
  - Voyage (Anthropic's recommended embedding model for Claude apps). Requires a
    Voyage API key, may not be Wix-enterprise approved.
  - Local sentence-transformers (all-MiniLM-L6-v2 or microsoft/codebert-base). Self-
    hosted, no external calls. Default fallback.

What we embed: the concatenation of (bug_summary, buggy_code, fix_diff). Bug
summary contributes semantic intent; buggy code contributes syntactic pattern;
fix diff disambiguates similar bugs with different root causes.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from rich.console import Console

from ..config import Config
from ..types import CorpusEntry

console = Console()


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray: ...
    @property
    def dim(self) -> int: ...


class LocalEmbedder:
    """Self-hosted sentence-transformers model. No external API calls."""

    def __init__(self, model_name: str = "microsoft/codebert-base") -> None:
        # Lazy import — keeps top-level deps light if user picks Voyage
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)
        self._dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

    @property
    def dim(self) -> int:
        return self._dim


class VoyageEmbedder:
    """Voyage AI embeddings — Anthropic's recommendation for code."""

    def __init__(self, api_key: str, model: str = "voyage-code-3") -> None:
        import voyageai
        self._client = voyageai.Client(api_key=api_key)
        self._model = model
        # voyage-code-3 returns 1024-dim by default
        self._dim = 1024

    def embed(self, texts: list[str]) -> np.ndarray:
        # Voyage caps batches at 128 texts
        out: list[list[float]] = []
        for i in range(0, len(texts), 128):
            batch = texts[i : i + 128]
            result = self._client.embed(batch, model=self._model, input_type="document")
            out.extend(result.embeddings)
        return np.array(out, dtype=np.float32)

    @property
    def dim(self) -> int:
        return self._dim


def build_embedder(config: Config) -> Embedder:
    """Factory based on config."""
    model = config["claude"].get("embedding_model", "local")
    if model.startswith("voyage"):
        import os
        return VoyageEmbedder(api_key=os.environ["VOYAGE_API_KEY"], model=model)
    return LocalEmbedder()


def embed_corpus(entries: list[CorpusEntry], embedder: Embedder) -> np.ndarray:
    """Returns array of shape (n, dim). Stores result back into entries in place."""
    texts = [_corpus_entry_to_embedding_text(e) for e in entries]
    console.log(f"Embedding {len(texts)} corpus entries with {embedder.__class__.__name__}")
    matrix = embedder.embed(texts)
    for entry, vec in zip(entries, matrix, strict=True):
        entry.embedding = vec.tolist()
    return matrix


def _corpus_entry_to_embedding_text(e: CorpusEntry) -> str:
    """Concatenate the signals we want clustered together."""
    parts = [
        f"# Bug summary\n{e.bug_summary}",
        f"# Language\n{e.language}",
        f"# Buggy code\n{e.buggy_code}",
        f"# Fix diff (first 2000 chars)\n{e.fix_diff[:2000]}",
        f"# Labels\n{', '.join(e.jira_labels)}",
    ]
    return "\n\n".join(parts)
