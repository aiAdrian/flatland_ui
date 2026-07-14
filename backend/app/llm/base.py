"""LLM provider seam.

One interface, three deployment targets (see `docs/reference/llm-setup.md`):

  - local           — a small model on the contributor's laptop (Ollama)
  - hosted API      — Claude via the official Anthropic SDK
  - cloud-hosted    — any OpenAI-compatible endpoint (vLLM / TGI / Ollama Cloud)

Consumers depend only on `LLMProvider`, never on a concrete provider, so the
model backing a feature can be swapped from config without touching the feature.
Register new providers in `app/llm/registry.py`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Sequence

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ProviderHealth:
    """Result of a cheap liveness probe — no token spend on any provider."""

    reachable: bool
    #: model ids the endpoint reports, when it can tell us
    models: list[str] | None = None
    #: populated when `reachable` is False; safe to show in the UI
    detail: str | None = None


class LLMProvider(ABC):
    """A chat-completion backend."""

    #: stable id (used by the registry and the `llm_provider` setting)
    id: str = "base"
    #: short human label
    label: str = "Base"
    #: one-line description
    description: str = ""

    def __init__(self, *, model: str, max_tokens: int, timeout_s: float) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s

    @abstractmethod
    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str | None = None,
    ) -> LLMResponse:
        """Single-shot completion. Raises `LLMError` on any provider failure."""
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> ProviderHealth:
        """Liveness probe. Must never raise — return `reachable=False` instead,
        so `/llm/providers` can report a dead backend rather than 500."""
        raise NotImplementedError


class LLMError(RuntimeError):
    """Any provider-side failure (unreachable, auth, rate limit, bad response).

    Providers wrap their SDK's exceptions in this so callers don't have to know
    which SDK is underneath.
    """
