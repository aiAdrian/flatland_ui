"""OpenAI-compatible chat provider — covers two of the three deployment targets.

Ollama, vLLM, TGI and Ollama Cloud all speak the OpenAI `/v1/chat/completions`
wire format, so the same client serves a laptop model and a GPU box; only the
base URL and the API key differ. `OllamaProvider` is this class with local
defaults.

Claude deliberately does NOT go through here — it uses the official Anthropic
SDK (see `app/llm/anthropic.py`), because the OpenAI shim would cost us tool-use
fidelity, prompt caching and adaptive thinking.
"""
from __future__ import annotations

from typing import Sequence

from openai import APIError, APIStatusError, AsyncOpenAI, OpenAIError

from app.llm.base import ChatMessage, LLMError, LLMProvider, LLMResponse, ProviderHealth


class OpenAICompatProvider(LLMProvider):
    id = "openai_compatible"
    label = "OpenAI-compatible endpoint"
    description = "Any OpenAI-compatible server (vLLM, TGI, Ollama Cloud, …). Set LLM_BASE_URL + LLM_API_KEY."

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        max_tokens: int,
        timeout_s: float,
        reasoning_effort: str = "none",
    ) -> None:
        super().__init__(model=model, max_tokens=max_tokens, timeout_s=timeout_s)
        self.base_url = base_url
        self.reasoning_effort = reasoning_effort
        # The OpenAI client rejects an empty key. Local Ollama ignores the value
        # entirely, so a placeholder keeps the no-auth case working.
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "not-needed",
            timeout=timeout_s,
            max_retries=1,
        )

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str | None = None,
    ) -> LLMResponse:
        payload = [{"role": m.role, "content": m.content} for m in messages]
        if system:
            payload.insert(0, {"role": "system", "content": system})

        extra: dict[str, object] = {}
        if self.reasoning_effort:
            # Thinking models (Qwen3.5, …) otherwise reason before answering, which
            # can consume the whole max_tokens budget and return empty content.
            extra["reasoning_effort"] = self.reasoning_effort

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=payload,
                max_tokens=self.max_tokens,
                **extra,
            )
        except APIStatusError as exc:
            raise LLMError(f"{self.id}: HTTP {exc.status_code} from {self.base_url}: {exc.message}") from exc
        except (APIError, OpenAIError) as exc:
            raise LLMError(f"{self.id}: {exc}") from exc

        choice = response.choices[0] if response.choices else None
        text = (choice.message.content if choice and choice.message else None) or ""
        usage = response.usage

        if not text.strip():
            # Don't hand a silent empty string to the caller. The usual cause is a
            # thinking model that spent max_tokens reasoning before answering.
            reason = choice.finish_reason if choice else "unknown"
            hint = (
                " — the model hit the token cap while reasoning; "
                "set LLM_REASONING_EFFORT=none or raise LLM_MAX_TOKENS"
                if reason == "length"
                else ""
            )
            raise LLMError(f"{self.id}: model '{self.model}' returned no text (finish_reason={reason}){hint}")

        return LLMResponse(
            text=text,
            provider=self.id,
            model=response.model or self.model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )

    async def health(self) -> ProviderHealth:
        try:
            listing = await self._client.models.list()
        except Exception as exc:  # noqa: BLE001 — health must never raise
            return ProviderHealth(reachable=False, detail=f"{type(exc).__name__}: {exc}")

        models = [m.id for m in listing.data]
        if self.model not in models:
            return ProviderHealth(
                reachable=False,
                models=models,
                detail=f"endpoint is up but has no model '{self.model}' (have: {', '.join(models) or 'none'})",
            )
        return ProviderHealth(reachable=True, models=models)


class OllamaProvider(OpenAICompatProvider):
    """Local Ollama. Same wire format, local defaults, no API key."""

    id = "ollama"
    label = "Ollama (local)"
    description = "Small model on your own machine. Needs `ollama serve` — see docs/reference/llm-setup.md."
