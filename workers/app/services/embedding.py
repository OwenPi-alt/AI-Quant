"""EmbeddingProvider abstraction.

Two providers ship today:

* DeterministicEmbedder — SHA-256 derived 1536-d unit vector. Zero cost,
  zero external dependency. Used by default so the system runs without
  any LLM provider configured. The output is byte-identical to the
  legacy `review._deterministic_embedding` helper, so existing pytest
  vectors keep passing.

* OpenAICompatEmbedder — POST {base_url}/v1/embeddings with an
  OpenAI-compatible body. Works with DeepSeek / OpenAI / Tongyi / Ollama
  embedding endpoints. Returns the first vector verbatim.

Switching is governed by Settings.embedding_provider.
"""

from __future__ import annotations

import hashlib
import logging
import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.settings import Settings

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_DIM = 1536


class EmbeddingProvider(ABC):
    """Pluggable async embedder. Always returns unit-normalised vector."""

    dim: int = DEFAULT_EMBEDDING_DIM

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        ...


class DeterministicEmbedder(EmbeddingProvider):
    """SHA-256 derived pseudo-embedding.

    Not semantic, but stable and free. Good enough for unit tests and for
    deployments where no real embedding API is configured. Output is
    byte-identical to the previous workers/app/workers/review.py helper.
    """

    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        self.dim = dim

    async def embed(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        out: list[float] = []
        for i in range(self.dim):
            byte = seed[i % len(seed)]
            rot = (byte + i * 31) & 0xFF
            out.append((rot / 255.0) - 0.5)
        norm = math.sqrt(sum(v * v for v in out)) or 1.0
        return [v / norm for v in out]


class OpenAICompatEmbedder(EmbeddingProvider):
    """Calls an OpenAI-compatible /v1/embeddings endpoint.

    Falls back to DeterministicEmbedder on any error so the trading loop
    never blocks on a flaky embedding provider.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dim: int = DEFAULT_EMBEDDING_DIM,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self.timeout = timeout
        self._fallback = DeterministicEmbedder(dim=dim)

    async def embed(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": self.model, "input": text},
                )
                response.raise_for_status()
                payload = response.json()
                vector = payload["data"][0]["embedding"]
                if not isinstance(vector, list) or not vector:
                    raise ValueError("empty embedding")
                length = len(vector)
                if length != self.dim:
                    logger.warning(
                        "embedding provider returned dim=%d but configured dim=%d; padding/truncating",
                        length,
                        self.dim,
                    )
                    if length < self.dim:
                        vector = list(vector) + [0.0] * (self.dim - length)
                    else:
                        vector = list(vector)[: self.dim]
                norm = math.sqrt(sum(float(v) * float(v) for v in vector)) or 1.0
                return [float(v) / norm for v in vector]
        except Exception:
            logger.exception("OpenAI-compatible embedding failed, falling back to deterministic")
            return await self._fallback.embed(text)


def make_embedder(settings: "Settings") -> EmbeddingProvider:
    provider = (settings.embedding_provider or "deterministic").lower().strip()
    if provider in {"openai", "openai_compat", "deepseek", "compat"}:
        if not settings.embedding_api_key:
            logger.warning(
                "embedding_provider=%s requested but EMBEDDING_API_KEY is empty; falling back to deterministic",
                provider,
            )
            return DeterministicEmbedder(dim=settings.embedding_dim)
        return OpenAICompatEmbedder(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            dim=settings.embedding_dim,
        )
    return DeterministicEmbedder(dim=settings.embedding_dim)
