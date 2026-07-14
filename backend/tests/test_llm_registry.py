"""Provider seam: registry wiring + the fake provider used by feature tests.

Everything here is hermetic — no model, no API key, no network. The one test
that talks to a real Ollama is in test_llm_live.py and skips itself when no
model is running.
"""
import asyncio
from typing import Sequence

import pytest

from app.config import Settings
from app.llm.base import ChatMessage, LLMError, LLMProvider, LLMResponse, ProviderHealth
from app.llm.registry import (
    active_provider,
    get_provider,
    provider_ids,
    provider_specs,
    reset_instances,
)


class FakeProvider(LLMProvider):
    """Stand-in for a real backend. Feature tests that need an LLM should use
    this rather than reaching for a running model."""

    id = "fake"
    label = "Fake"
    description = "Deterministic provider for tests."

    def __init__(self, *, reply: str = "ok", fail: bool = False) -> None:
        super().__init__(model="fake-model", max_tokens=128, timeout_s=1.0)
        self.reply = reply
        self.fail = fail
        self.seen: list[Sequence[ChatMessage]] = []
        self.seen_system: list[str | None] = []

    async def complete(self, messages, *, system=None) -> LLMResponse:
        if self.fail:
            raise LLMError("fake: boom")
        self.seen.append(list(messages))
        self.seen_system.append(system)
        return LLMResponse(
            text=self.reply,
            provider=self.id,
            model=self.model,
            input_tokens=1,
            output_tokens=2,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(reachable=not self.fail, models=[self.model])


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_instances()
    yield
    reset_instances()


def test_all_three_targets_are_registered():
    # local, hosted API, cloud-hosted — the three deployment targets.
    assert set(provider_ids()) == {"ollama", "anthropic", "openai_compatible"}


def test_specs_carry_ui_metadata():
    for spec in provider_specs():
        assert spec.label
        assert spec.description
    by_id = {s.id: s for s in provider_specs()}
    assert by_id["ollama"].requires_api_key is False
    assert by_id["anthropic"].requires_api_key is True


def test_unknown_provider_raises():
    with pytest.raises(KeyError):
        get_provider("nope")


def test_active_provider_follows_settings():
    cfg = Settings(llm_provider="ollama", llm_model="qwen3.5:4b")
    assert active_provider(cfg).id == "ollama"

    reset_instances()
    cfg = Settings(llm_provider="anthropic", llm_model="claude-opus-4-8", llm_api_key="x")
    assert active_provider(cfg).id == "anthropic"


def test_provider_config_is_applied():
    cfg = Settings(
        llm_provider="openai_compatible",
        llm_model="Qwen/Qwen3.5-9B",
        llm_base_url="https://gpu.example.org/v1",
        llm_api_key="secret",
        llm_max_tokens=256,
    )
    provider = active_provider(cfg)
    assert provider.model == "Qwen/Qwen3.5-9B"
    assert provider.base_url == "https://gpu.example.org/v1"
    assert provider.max_tokens == 256


def test_instances_are_reused():
    # Each provider owns an HTTP connection pool; we must not build one per call.
    cfg = Settings()
    assert get_provider("ollama", cfg) is get_provider("ollama", cfg)


def test_health_never_raises_on_a_dead_endpoint():
    # Port 1 refuses instantly — stands in for "Ollama isn't running".
    cfg = Settings(llm_provider="ollama", llm_base_url="http://127.0.0.1:1/v1", llm_timeout_s=2.0)
    result = asyncio.run(active_provider(cfg).health())
    assert result.reachable is False
    assert result.detail  # something showable in the UI


def test_anthropic_health_reports_missing_key_without_calling_out():
    cfg = Settings(llm_provider="anthropic", llm_model="claude-opus-4-8", llm_api_key="")
    result = asyncio.run(active_provider(cfg).health())
    assert result.reachable is False
    assert "API key" in (result.detail or "")


def test_thinking_is_off_by_default_for_local_models():
    # Qwen3.5 & co. reason before answering. Left on, a trivial prompt spends the
    # whole token budget on chain-of-thought and returns *empty* content — so the
    # laptop default must ask for a direct answer.
    assert Settings().llm_reasoning_effort == "none"


def test_empty_answer_raises_instead_of_returning_an_empty_string():
    """A thinking model that exhausts max_tokens returns content='' with
    finish_reason='length'. That must be an error, not a silent empty answer."""

    class _Msg:
        content = ""

    class _Choice:
        message = _Msg()
        finish_reason = "length"

    class _Response:
        choices = [_Choice()]
        usage = None
        model = "qwen3.5:4b"

    async def _fake_create(**_kwargs):
        return _Response()

    provider = active_provider(Settings(llm_provider="ollama"))
    provider._client.chat.completions.create = _fake_create  # type: ignore[method-assign]

    with pytest.raises(LLMError) as exc:
        asyncio.run(provider.complete([ChatMessage(role="user", content="hi")]))
    assert "LLM_REASONING_EFFORT" in str(exc.value)  # actionable, not just "failed"


def test_fake_provider_satisfies_the_interface():
    fake = FakeProvider(reply="hello")
    result = asyncio.run(fake.complete([ChatMessage(role="user", content="hi")]))
    assert result.text == "hello"
    assert result.provider == "fake"

    failing = FakeProvider(fail=True)
    with pytest.raises(LLMError):
        asyncio.run(failing.complete([ChatMessage(role="user", content="hi")]))
