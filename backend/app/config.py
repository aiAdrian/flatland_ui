from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    log_level: str = "info"
    cors_origins: str = "http://localhost:4200"

    # --- LLM seam (see docs/reference/llm-setup.md) ---
    #: which registered provider to use: ollama | anthropic | openai_compatible
    llm_provider: str = "ollama"
    #: provider-specific model id, e.g. "qwen3.5:4b" or "claude-opus-4-8"
    llm_model: str = "qwen3.5:4b"
    #: OpenAI-compatible endpoint; ignored by the anthropic provider
    llm_base_url: str = "http://localhost:11434/v1"
    #: unused for local Ollama; the Anthropic SDK also reads ANTHROPIC_API_KEY
    llm_api_key: str = ""
    #: hard cap on output tokens. Headroom for Claude's adaptive thinking, which
    #: shares this budget with the visible answer.
    llm_max_tokens: int = 8192
    #: Anthropic only — thinking depth: low | medium | high | xhigh | max
    llm_effort: str = "medium"
    #: OpenAI-compatible providers only. Qwen3.5 and friends are *thinking* models
    #: and reason by default, which on a laptop means tens of seconds and a budget
    #: spent before any answer is produced. "none" makes them answer directly.
    #: none | low | medium | high; empty string omits the field entirely (for
    #: endpoints that reject it).
    llm_reasoning_effort: str = "none"
    llm_timeout_s: float = 120.0

    # --- Docs Q&A / RAG (see docs/reference/llm-setup.md) ---
    #: ground /llm/chat answers in the repo's markdown docs
    rag_enabled: bool = True
    #: embedding model, served by the OpenAI-compatible endpoint below
    rag_embed_model: str = "nomic-embed-text"
    #: independent of the chat provider: retrieval stays local even when
    #: LLM_PROVIDER points at Claude or a cloud endpoint
    rag_embed_base_url: str = "http://localhost:11434/v1"
    #: docs snippets handed to the model per question
    rag_top_k: int = 4
    #: corpus roots, comma-separated, relative to the repo root. Excludes
    #: docs/plans/, which describes features that do not exist yet.
    rag_docs: str = "README.md,PLAYGROUND.md,docs/README.md,docs/reference,docs/scenarios"


settings = Settings()
