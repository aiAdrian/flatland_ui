"""Central LLM provider registry — runtime construction + UI metadata.

Mirrors `app/policies/registry.py`: a spec per provider, a factory, and lookup
helpers. The active provider is resolved from `Settings.llm_provider`, so
switching from a laptop model to Claude is an `.env` change, not a code change.

Add a provider by implementing `LLMProvider` and registering a spec here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.config import Settings, settings
from app.llm.anthropic import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.openai_compat import OllamaProvider, OpenAICompatProvider

ProviderFactory = Callable[[Settings], LLMProvider]


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    description: str
    requires_api_key: bool
    factory: ProviderFactory


def _mk_ollama(cfg: Settings) -> LLMProvider:
    return OllamaProvider(
        model=cfg.llm_model,
        base_url=cfg.llm_base_url,
        api_key="",
        max_tokens=cfg.llm_max_tokens,
        timeout_s=cfg.llm_timeout_s,
        reasoning_effort=cfg.llm_reasoning_effort,
    )


def _mk_openai_compat(cfg: Settings) -> LLMProvider:
    return OpenAICompatProvider(
        model=cfg.llm_model,
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        max_tokens=cfg.llm_max_tokens,
        timeout_s=cfg.llm_timeout_s,
        reasoning_effort=cfg.llm_reasoning_effort,
    )


def _mk_anthropic(cfg: Settings) -> LLMProvider:
    return AnthropicProvider(
        model=cfg.llm_model,
        api_key=cfg.llm_api_key,
        max_tokens=cfg.llm_max_tokens,
        timeout_s=cfg.llm_timeout_s,
        effort=cfg.llm_effort,
    )


_REGISTRY: dict[str, ProviderSpec] = {
    "ollama": ProviderSpec(
        id="ollama",
        label=OllamaProvider.label,
        description=OllamaProvider.description,
        requires_api_key=False,
        factory=_mk_ollama,
    ),
    "anthropic": ProviderSpec(
        id="anthropic",
        label=AnthropicProvider.label,
        description=AnthropicProvider.description,
        requires_api_key=True,
        factory=_mk_anthropic,
    ),
    "openai_compatible": ProviderSpec(
        id="openai_compatible",
        label=OpenAICompatProvider.label,
        description=OpenAICompatProvider.description,
        requires_api_key=True,
        factory=_mk_openai_compat,
    ),
}

#: Built providers, keyed by id. Each holds an HTTP client, so we build lazily
#: and reuse rather than opening a new connection pool per request.
_instances: dict[str, LLMProvider] = {}


def provider_ids() -> list[str]:
    return list(_REGISTRY.keys())


def provider_specs() -> list[ProviderSpec]:
    return list(_REGISTRY.values())


def get_provider_spec(provider_id: str) -> ProviderSpec | None:
    return _REGISTRY.get(provider_id)


def get_provider(provider_id: str, cfg: Settings | None = None) -> LLMProvider:
    """Build (or reuse) the provider with this id. Raises KeyError if unknown."""
    spec = _REGISTRY.get(provider_id)
    if spec is None:
        raise KeyError(provider_id)
    if provider_id not in _instances:
        _instances[provider_id] = spec.factory(cfg or settings)
    return _instances[provider_id]


def active_provider(cfg: Settings | None = None) -> LLMProvider:
    """The provider selected by `LLM_PROVIDER`."""
    cfg = cfg or settings
    return get_provider(cfg.llm_provider, cfg)


def reset_instances() -> None:
    """Drop cached provider instances — used by tests that vary the settings."""
    _instances.clear()
