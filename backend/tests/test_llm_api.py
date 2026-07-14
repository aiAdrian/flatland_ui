"""/llm/* API contract. Hermetic: the active provider is swapped for a fake."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_llm_registry import FakeProvider

client = TestClient(app)


@pytest.fixture(autouse=True)
def _ungrounded_chat(monkeypatch):
    """Keep these contract tests hermetic: /llm/chat grounds in the docs index
    by default, which would build a real index and call the embedder. Grounding
    has its own tests in test_rag_api.py."""

    async def no_index(cfg):
        return None

    monkeypatch.setattr("app.api.llm.docs_index", no_index)


def test_providers_lists_all_three_and_marks_the_active_one():
    r = client.get("/llm/providers")
    assert r.status_code == 200, r.text
    body = r.json()

    ids = {p["id"] for p in body["providers"]}
    assert ids == {"ollama", "anthropic", "openai_compatible"}

    active = [p for p in body["providers"] if p["is_active"]]
    assert len(active) == 1
    assert active[0]["id"] == body["active"]


def test_health_of_unknown_provider_is_404():
    r = client.get("/llm/health", params={"provider": "nope"})
    assert r.status_code == 404


def test_health_reports_a_dead_backend_as_200_not_500(monkeypatch):
    # An unreachable model is a state to display, not a server error.
    monkeypatch.setattr("app.api.llm.active_provider", lambda cfg: FakeProvider(fail=True))
    r = client.get("/llm/health")
    assert r.status_code == 200, r.text
    assert r.json()["reachable"] is False


def test_complete_returns_text_and_usage(monkeypatch):
    fake = FakeProvider(reply="Train 3 should hold at the junction.")
    monkeypatch.setattr("app.api.llm.active_provider", lambda cfg: fake)

    r = client.post("/llm/complete", json={"prompt": "What should train 3 do?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "Train 3 should hold at the junction."
    assert body["provider"] == "fake"
    assert body["output_tokens"] == 2

    # The prompt actually reached the provider.
    assert fake.seen[0][0].content == "What should train 3 do?"


def test_provider_failure_surfaces_as_502(monkeypatch):
    monkeypatch.setattr("app.api.llm.active_provider", lambda cfg: FakeProvider(fail=True))
    r = client.post("/llm/complete", json={"prompt": "hi"})
    assert r.status_code == 502
    assert "boom" in r.json()["detail"]


def test_empty_prompt_is_rejected():
    r = client.post("/llm/complete", json={"prompt": ""})
    assert r.status_code == 422


def test_chat_passes_the_whole_transcript_to_the_model(monkeypatch):
    # The UI chat panel resends the history each turn — the model must see it all,
    # or it answers follow-ups with no memory of what was said.
    fake = FakeProvider(reply="Because train 3 has right of way.")
    monkeypatch.setattr("app.api.llm.active_provider", lambda cfg: fake)

    r = client.post(
        "/llm/chat",
        json={
            "messages": [
                {"role": "user", "content": "Should train 3 hold?"},
                {"role": "assistant", "content": "Yes, hold."},
                {"role": "user", "content": "Why?"},
            ],
            "system": "You are a railway dispatcher assistant.",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "Because train 3 has right of way."

    seen = fake.seen[0]
    assert [m.role for m in seen] == ["user", "assistant", "user"]
    assert seen[-1].content == "Why?"


def test_chat_requires_at_least_one_message():
    r = client.post("/llm/chat", json={"messages": []})
    assert r.status_code == 422


def test_chat_provider_failure_surfaces_as_502(monkeypatch):
    monkeypatch.setattr("app.api.llm.active_provider", lambda cfg: FakeProvider(fail=True))
    r = client.post("/llm/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 502
