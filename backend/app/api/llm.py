"""LLM provider discovery + a smoke-test completion endpoint.

`GET /llm/providers` mirrors `GET /policies`: it tells the frontend (and a
contributor verifying their setup) which backends exist and which one is live.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.llm.base import ChatMessage, LLMError
from app.llm.registry import active_provider, get_provider, provider_specs
from app.rag.index import docs_index

logger = logging.getLogger(__name__)

router = APIRouter()


class ProviderInfo(BaseModel):
    id: str
    label: str
    description: str
    requires_api_key: bool
    is_active: bool


class ProvidersResponse(BaseModel):
    active: str
    model: str
    providers: list[ProviderInfo]


class HealthResponse(BaseModel):
    provider: str
    model: str
    reachable: bool
    models: list[str] | None = None
    detail: str | None = None


class CompleteRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    system: str | None = None


class CompleteResponse(BaseModel):
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    #: docs snippets the answer was grounded in ("path › heading"). Only /llm/chat
    #: with use_docs sets this; None means the answer is ungrounded.
    sources: list[str] | None = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    """A whole transcript. The API is stateless — the client owns the history and
    resends it, which keeps the backend free of per-user conversation state."""

    messages: list[ChatTurn] = Field(..., min_length=1)
    system: str | None = None
    #: ground the answer in the repo docs (docs/reference/llm-setup.md)
    use_docs: bool = True


@router.get("/llm/providers", response_model=ProvidersResponse, tags=["llm"])
def list_providers() -> ProvidersResponse:
    return ProvidersResponse(
        active=settings.llm_provider,
        model=settings.llm_model,
        providers=[
            ProviderInfo(
                id=spec.id,
                label=spec.label,
                description=spec.description,
                requires_api_key=spec.requires_api_key,
                is_active=spec.id == settings.llm_provider,
            )
            for spec in provider_specs()
        ],
    )


@router.get("/llm/health", response_model=HealthResponse, tags=["llm"])
async def llm_health(provider: str | None = None) -> HealthResponse:
    """Cheap liveness probe against a provider (default: the active one).
    Spends no tokens. Returns 200 with `reachable: false` for a dead backend —
    an unreachable model is a state to display, not a server error."""
    try:
        backend = get_provider(provider, settings) if provider else active_provider(settings)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown llm provider '{provider}'")

    result = await backend.health()
    return HealthResponse(
        provider=backend.id,
        model=backend.model,
        reachable=result.reachable,
        models=result.models,
        detail=result.detail,
    )


@router.post("/llm/complete", response_model=CompleteResponse, tags=["llm"])
async def complete(request: CompleteRequest) -> CompleteResponse:
    """One-shot completion on the active provider. This is the seam's smoke test;
    real features should depend on `LLMProvider`, not on this route."""
    return await _run(
        [ChatMessage(role="user", content=request.prompt)],
        system=request.system,
    )


@router.post("/llm/chat", response_model=CompleteResponse, tags=["llm"])
async def chat(request: ChatRequest) -> CompleteResponse:
    """Multi-turn chat — what the UI chat panel calls. Same provider seam, but the
    client sends the whole transcript so the model has the conversation context.
    By default the last user turn is answered grounded in the repo docs (§9)."""
    system = request.system
    sources: list[str] | None = None
    if request.use_docs:
        question = next((t.content for t in reversed(request.messages) if t.role == "user"), None)
        if question:
            grounding, sources = await _grounding_for(question, context=_history_window(request.messages))
            if grounding:
                system = f"{system}\n\n{grounding}" if system else grounding

    return await _run(
        [ChatMessage(role=turn.role, content=turn.content) for turn in request.messages],
        system=system,
        sources=sources,
    )


class RagStatus(BaseModel):
    enabled: bool
    files: int = 0
    chunks: int = 0
    embed_model: str
    #: False = keyword-only retrieval (embedding endpoint or model unavailable)
    embeddings_available: bool = False
    detail: str | None = None


@router.get("/llm/rag/status", response_model=RagStatus, tags=["llm"])
async def rag_status() -> RagStatus:
    """Verification surface for the docs index — builds it if needed."""
    if not settings.rag_enabled:
        return RagStatus(enabled=False, embed_model=settings.rag_embed_model, detail="disabled via RAG_ENABLED")
    index = await docs_index(settings)
    return RagStatus(
        enabled=True,
        files=index.files if index else 0,
        chunks=len(index.chunks) if index else 0,
        embed_model=settings.rag_embed_model,
        embeddings_available=bool(index and index.embeddings_available),
        detail=None if index and index.embeddings_available
        else f"embedding model '{settings.rag_embed_model}' unreachable — keyword-only retrieval "
             f"(ollama pull {settings.rag_embed_model})",
    )


_GROUNDING_PREAMBLE = (
    "Excerpts from the project documentation are below. Ground your answer in them: "
    "use what they say and name the file it came from. If they do not cover the "
    "question, say so plainly instead of guessing.\n\n"
)


#: how much recent conversation feeds retrieval alongside the question
_HISTORY_TURNS = 4
_HISTORY_CHARS = 1200


def _history_window(messages: list[ChatTurn]) -> str | None:
    """The turns before the final question, newest kept when truncating. Lets
    retrieval resolve follow-ups such as "how do I do that?"."""
    history = [t.content for t in messages[:-1][-_HISTORY_TURNS:]]
    if not history:
        return None
    return "\n".join(history)[-_HISTORY_CHARS:]


async def _grounding_for(question: str, *, context: str | None = None) -> tuple[str | None, list[str] | None]:
    """Docs context for one question. Retrieval must never break chat: any
    failure here means answering ungrounded, not answering 5xx."""
    try:
        index = await docs_index(settings)
        if index is None:
            return None, None
        snippets = await index.retrieve(question, k=settings.rag_top_k, context=context)
    except Exception:  # noqa: BLE001
        logger.exception("docs retrieval failed — answering ungrounded")
        return None, None
    if not snippets:
        return None, None

    block = "\n\n---\n\n".join(s.text for s in snippets)
    labels = list(dict.fromkeys(s.label for s in snippets))
    return _GROUNDING_PREAMBLE + block, labels


async def _run(
    messages: list[ChatMessage],
    *,
    system: str | None,
    sources: list[str] | None = None,
) -> CompleteResponse:
    backend = active_provider(settings)
    try:
        result = await backend.complete(messages, system=system)
    except LLMError as exc:
        # 502: we are the gateway, and the model behind us failed.
        raise HTTPException(status_code=502, detail=str(exc))

    return CompleteResponse(
        text=result.text,
        provider=result.provider,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        sources=sources,
    )
