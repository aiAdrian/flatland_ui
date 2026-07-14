"""Claude via the official Anthropic SDK.

Deliberately not routed through the OpenAI-compatible adapter: the shim would
normalise away adaptive thinking, prompt caching and full tool-use fidelity —
the things we would actually be paying Claude for.

Current-model constraints (Opus 4.x / Sonnet 5): `temperature`, `top_p` and
`thinking.budget_tokens` are rejected with HTTP 400. Thinking depth is
controlled by adaptive thinking plus `output_config.effort`, not a token budget.
"""
from __future__ import annotations

from typing import Sequence

from anthropic import AsyncAnthropic, AnthropicError, APIStatusError

from app.llm.base import ChatMessage, LLMError, LLMProvider, LLMResponse, ProviderHealth


class AnthropicProvider(LLMProvider):
    id = "anthropic"
    label = "Claude (Anthropic API)"
    description = "Hosted Claude model. Needs ANTHROPIC_API_KEY (or LLM_API_KEY)."

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        max_tokens: int,
        timeout_s: float,
        effort: str = "medium",
    ) -> None:
        super().__init__(model=model, max_tokens=max_tokens, timeout_s=timeout_s)
        self.effort = effort
        self._api_key = api_key
        # An empty key is allowed here so the provider can still be listed and
        # report `reachable=False` via /llm/providers instead of blowing up at
        # import time. The SDK also picks up ANTHROPIC_API_KEY on its own.
        self._client = AsyncAnthropic(
            api_key=api_key or None,
            timeout=timeout_s,
            max_retries=1,
        )

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str | None = None,
    ) -> LLMResponse:
        # Anthropic takes the system prompt as a top-level arg, not a message.
        turns = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        leading_system = "\n\n".join(m.content for m in messages if m.role == "system")
        system_prompt = "\n\n".join(p for p in (system, leading_system) if p)

        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt or None,
                messages=turns,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
            )
        except APIStatusError as exc:
            raise LLMError(f"{self.id}: HTTP {exc.status_code}: {exc.message}") from exc
        except AnthropicError as exc:
            raise LLMError(f"{self.id}: {exc}") from exc

        if response.stop_reason == "refusal":
            raise LLMError(f"{self.id}: request was declined by the model's safety classifiers")

        # Content is a list of blocks (thinking, text, …) — take the text ones.
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            text=text,
            provider=self.id,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def health(self) -> ProviderHealth:
        if not (self._api_key or self._client.api_key):
            return ProviderHealth(reachable=False, detail="no API key set (LLM_API_KEY / ANTHROPIC_API_KEY)")
        try:
            # Free call — validates the key without spending tokens.
            listing = await self._client.models.list()
        except Exception as exc:  # noqa: BLE001 — health must never raise
            return ProviderHealth(reachable=False, detail=f"{type(exc).__name__}: {exc}")

        return ProviderHealth(reachable=True, models=[m.id for m in listing.data])
