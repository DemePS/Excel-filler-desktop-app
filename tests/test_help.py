"""The Help button: one answer of the model about using the app, from the guide, with no tools."""

import pytest
from fastapi.testclient import TestClient

from coding_agent import config
from excel_filler import help as help_guide
from excel_filler.desktop import server
from excel_filler.desktop.server import create_app
from excel_filler.desktop.settings import MemoryStore, Settings

TOKEN = "t0ken"


class FakeClient:
    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        block = type("B", (), {"type": "text", "text": "Tick “Work on a copy”."})()
        return type("R", (), {"content": [block]})()


@pytest.fixture
def helped(tmp_path, monkeypatch):
    for name in ("ANTHROPIC_FOUNDRY_ENDPOINT", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "CODEAGENT_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    config.clear()
    settings = Settings(MemoryStore(), tmp_path / "s.json")
    client = TestClient(create_app(TOKEN, settings=settings), headers={"x-token": TOKEN})
    fake = FakeClient()
    monkeypatch.setattr(server.session, "_get_client", lambda: fake)
    yield client, settings, fake
    import os
    for name in ("DEEPSEEK_API_KEY", "CODEAGENT_PROVIDER"):
        os.environ.pop(name, None)
    config.clear()


def test_help_needs_a_key_first(helped):
    client, _, fake = helped
    assert client.post("/api/help", json={"question": "How?"}).status_code == 409
    assert fake.calls == []


def test_help_answers_with_the_guide_and_no_tools(helped):
    client, settings, fake = helped
    settings.save("sk-" + "x" * 30)
    r = client.post("/api/help", json={"question": "How do I keep the original?", "language": "fr",
                                       "history": [{"role": "user", "text": "Hello"}, {"role": "assistant", "text": "Hi"}]})
    assert r.status_code == 200 and r.json()["answer"] == "Tick “Work on a copy”."
    call = fake.calls[0]
    assert "tools" not in call and "ComptaIA" in call["system"] and "Answer in French" in call["system"]
    assert [m["role"] for m in call["messages"]] == ["user", "assistant", "user"]
    assert call["messages"][-1]["content"] == "How do I keep the original?"
    assert call["model"] == config.DEEPSEEK_MODEL


def test_help_refuses_an_empty_or_long_question(helped):
    client, settings, _ = helped
    settings.save("sk-" + "x" * 30)
    assert client.post("/api/help", json={"question": "  "}).status_code == 400
    assert client.post("/api/help", json={"question": "x" * (help_guide.MAX_QUESTION + 1)}).status_code == 400


def test_history_is_bounded_and_alternating():
    history = [{"role": "assistant", "text": "stray"}] + [{"role": "user", "text": f"q{i}"} for i in range(12)]
    kept = help_guide.clean_history(history)
    assert len(kept) <= 1 and kept[0]["role"] == "user" and "q11" in kept[0]["content"]   # merged: no two user turns in a row
