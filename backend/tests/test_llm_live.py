"""End-to-end check against a *real* local model.

Skips itself when Ollama isn't running or the model isn't pulled, so CI and
contributors without a model stay green. Run `scripts/setup-llm.sh` to enable it.
"""
import asyncio

import httpx
import pytest

from app.config import Settings
from app.llm.base import ChatMessage
from app.llm.registry import active_provider, reset_instances

CFG = Settings()


def _ollama_has_model() -> bool:
    if CFG.llm_provider != "ollama":
        return False
    try:
        r = httpx.get(f"{CFG.llm_base_url}/models", timeout=2.0)
        r.raise_for_status()
    except Exception:
        return False
    return CFG.llm_model in {m["id"] for m in r.json().get("data", [])}


requires_local_model = pytest.mark.skipif(
    not _ollama_has_model(),
    reason=f"no local Ollama serving '{CFG.llm_model}' — run scripts/setup-llm.sh",
)


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_instances()
    yield
    reset_instances()


@requires_local_model
@pytest.mark.integration
def test_local_model_is_reachable():
    result = asyncio.run(active_provider(CFG).health())
    assert result.reachable is True, result.detail
    assert CFG.llm_model in (result.models or [])


@requires_local_model
@pytest.mark.integration
def test_local_model_completes_a_prompt():
    provider = active_provider(CFG)
    result = asyncio.run(
        provider.complete(
            [ChatMessage(role="user", content="Reply with exactly one word: dispatcher")],
            system="You answer with a single word and no punctuation.",
        )
    )
    assert result.text.strip(), "model returned no text"
    assert result.provider == "ollama"
    assert (result.output_tokens or 0) > 0
