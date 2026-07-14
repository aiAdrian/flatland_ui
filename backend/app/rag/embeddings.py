"""Embeddings via the OpenAI-compatible `/v1/embeddings` endpoint.

Ollama serves this natively, so retrieval reuses the wire format — and the
already-running server — that the chat seam depends on. It is configured
independently of the *chat* provider (`RAG_EMBED_BASE_URL`), so pointing
`LLM_PROVIDER` at Claude or a cloud box keeps retrieval local and free.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
from openai import AsyncOpenAI, OpenAIError

#: Ollama handles list inputs; batching bounds a single request's size anyway
_BATCH = 64


class EmbeddingsUnavailable(RuntimeError):
    """The embedding endpoint or model is not usable right now.

    Callers degrade to keyword-only retrieval — they must not fail the chat.
    """


class Embedder:
    def __init__(self, *, model: str, base_url: str, timeout_s: float) -> None:
        self.model = model
        # Same placeholder-key trick as OpenAICompatProvider: local Ollama
        # ignores the value, the client just refuses an empty one.
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key="not-needed",
            timeout=timeout_s,
            max_retries=1,
        )

    async def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Unit-normalised float32 vectors, one row per input text (in order)."""
        rows: list[list[float]] = []
        try:
            for start in range(0, len(texts), _BATCH):
                batch = list(texts[start : start + _BATCH])
                response = await self._client.embeddings.create(model=self.model, input=batch)
                rows.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        except OpenAIError as exc:
            raise EmbeddingsUnavailable(f"embedding model '{self.model}': {exc}") from exc

        vectors = np.asarray(rows, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms
