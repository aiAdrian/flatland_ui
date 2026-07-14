"""Docs grounding on /llm/chat + /llm/rag/status. Hermetic: fake index, fake
provider — retrieval behaviour itself is covered in test_rag_index.py."""
from fastapi.testclient import TestClient

from app.main import app
from app.rag.index import Snippet
from tests.test_llm_registry import FakeProvider

client = TestClient(app)

SNIPPET = Snippet(
    source="docs/reference/llm-setup.md",
    heading="Troubleshooting",
    text="docs/reference/llm-setup.md › Troubleshooting\n\nRestart the server.",
)


class FakeIndex:
    files = 1
    chunks = [SNIPPET]
    embeddings_available = True

    def __init__(self):
        self.seen: list[tuple[str, str | None]] = []

    async def retrieve(self, query, k, *, context=None):
        self.seen.append((query, context))
        return [SNIPPET]


def _use_index(monkeypatch, index):
    async def fake(cfg):
        return index

    monkeypatch.setattr("app.api.llm.docs_index", fake)


def test_chat_grounds_in_the_docs_and_reports_sources(monkeypatch):
    fake = FakeProvider(reply="Restart it.")
    monkeypatch.setattr("app.api.llm.active_provider", lambda cfg: fake)
    _use_index(monkeypatch, FakeIndex())

    r = client.post(
        "/llm/chat",
        json={"messages": [{"role": "user", "content": "server is down?"}], "system": "Be brief."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["sources"] == ["docs/reference/llm-setup.md › Troubleshooting"]

    # The excerpt went into the system prompt, after the caller's own prompt.
    system = fake.seen_system[0]
    assert system.startswith("Be brief.")
    assert "Restart the server." in system


def test_follow_ups_retrieve_with_the_conversation_history(monkeypatch):
    # "How do I do that?" is meaningless alone — the earlier turns carry the topic.
    fake = FakeProvider()
    monkeypatch.setattr("app.api.llm.active_provider", lambda cfg: fake)
    index = FakeIndex()
    _use_index(monkeypatch, index)

    r = client.post(
        "/llm/chat",
        json={
            "messages": [
                {"role": "user", "content": "What does Director mode do?"},
                {"role": "assistant", "content": "It runs the AI on directives."},
                {"role": "user", "content": "How do I switch to it?"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    query, context = index.seen[0]
    assert query == "How do I switch to it?"
    assert "Director mode" in context and "directives" in context
    assert "How do I switch to it?" not in context  # the question is not its own context


def test_first_question_has_no_history_context(monkeypatch):
    monkeypatch.setattr("app.api.llm.active_provider", lambda cfg: FakeProvider())
    index = FakeIndex()
    _use_index(monkeypatch, index)

    client.post("/llm/chat", json={"messages": [{"role": "user", "content": "hi there friend"}]})
    assert index.seen[0] == ("hi there friend", None)


def test_use_docs_false_skips_retrieval(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr("app.api.llm.active_provider", lambda cfg: fake)

    async def exploding_index(cfg):
        raise AssertionError("retrieval must not run when use_docs is false")

    monkeypatch.setattr("app.api.llm.docs_index", exploding_index)

    r = client.post(
        "/llm/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "use_docs": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["sources"] is None


def test_retrieval_failure_never_breaks_chat(monkeypatch):
    fake = FakeProvider(reply="still here")
    monkeypatch.setattr("app.api.llm.active_provider", lambda cfg: fake)

    async def broken(cfg):
        raise RuntimeError("index exploded")

    monkeypatch.setattr("app.api.llm.docs_index", broken)

    r = client.post("/llm/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "still here"
    assert r.json()["sources"] is None
    assert fake.seen_system[0] is None  # answered ungrounded, not half-grounded


def test_rag_status_reports_the_index(monkeypatch):
    _use_index(monkeypatch, FakeIndex())
    r = client.get("/llm/rag/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is True
    assert body["files"] == 1
    assert body["chunks"] == 1
    assert body["embeddings_available"] is True
    assert body["detail"] is None


def test_rag_status_flags_keyword_only_mode(monkeypatch):
    index = FakeIndex()
    index.embeddings_available = False
    _use_index(monkeypatch, index)
    r = client.get("/llm/rag/status")
    body = r.json()
    assert body["embeddings_available"] is False
    assert "ollama pull" in body["detail"]


def test_rag_disabled_is_a_state_not_an_error(monkeypatch):
    monkeypatch.setattr("app.api.llm.settings.rag_enabled", False)
    r = client.get("/llm/rag/status")
    assert r.status_code == 200
    assert r.json()["enabled"] is False
