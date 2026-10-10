"""The Settings endpoints: the API key is tested, saved, used, and never shown or logged."""

import logging
import os

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from coding_agent import config
from excel_filler.desktop import server
from excel_filler.desktop.server import create_app
from excel_filler.desktop.settings import MemoryStore, Settings

REAL_TEST_KEY = server.test_key  # the fixture replaces it in the module
TOKEN = "t0ken"
KEY = "sk-" + "x" * 30


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ("ANTHROPIC_FOUNDRY_ENDPOINT", "ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
                 "DEEPSEEK_API_KEY", "CODEAGENT_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    config.clear()
    calls = []
    monkeypatch.setattr(server, "test_key", lambda key: calls.append(key))
    yield tmp_path, monkeypatch, calls
    for name in ("DEEPSEEK_API_KEY", "CODEAGENT_PROVIDER"):  # the settings write them into the process
        os.environ.pop(name, None)
    config.clear()


@pytest.fixture
def parts(env):
    tmp_path, _, _ = env
    store = MemoryStore()
    settings = Settings(store, tmp_path / "settings.json")
    client = TestClient(create_app(TOKEN, settings=settings), headers={"x-token": TOKEN})
    return client, settings, store


def test_nothing_set_up(parts):
    client, _, _ = parts
    info = client.get("/api/settings").json()
    assert info["configured"] is False and info["source"] == "none" and info["storage"] == "session"
    assert "Settings" in client.get("/api/state").json()["connection_problem"]
    assert client.post("/api/job", json={"workbook": "a.xlsx"}).status_code == 400


def test_save_then_use(parts, env):
    client, settings, store = parts
    r = client.post("/api/settings", json={"api_key": f"  {KEY}  "})
    assert r.status_code == 200
    assert r.json()["configured"] and r.json()["source"] == "saved" and r.json()["key_hint"] == KEY[-4:]
    assert KEY not in r.text and KEY not in client.get("/api/settings").text
    assert store.get() == KEY and env[2] == [KEY]
    assert config.current_api_key() == KEY and config.active_provider() == "deepseek" and config.get_model() == config.DEEPSEEK_MODEL
    assert client.get("/api/state").json()["connection_problem"] is None


def test_bad_format_is_not_saved_nor_tested(parts, env):
    client, _, store = parts
    assert client.post("/api/settings", json={"api_key": "short"}).status_code == 400
    assert client.post("/api/settings", json={"api_key": "has space " + KEY}).status_code == 400
    assert store.get() is None and env[2] == []


def test_a_failing_test_call_saves_nothing(parts, env):
    client, _, store = parts
    from fastapi import HTTPException

    def reject(key):
        raise HTTPException(401, "DeepSeek did not accept this key.")
    env[1].setattr(server, "test_key", reject)
    assert client.post("/api/settings", json={"api_key": KEY}).status_code == 401
    assert store.get() is None and config.current_api_key() is None


def test_remove_falls_back(parts, env):
    client, _, store = parts
    env[1].setenv("ANTHROPIC_FOUNDRY_ENDPOINT", "https://x.services.ai.azure.com/anthropic")
    client.post("/api/settings", json={"api_key": KEY})
    assert config.active_provider() == "deepseek"
    info = client.delete("/api/settings/key").json()
    assert store.get() is None and config.active_provider() == "foundry" and info["source"] == "foundry"


def test_refused_while_a_job_runs(parts):
    client, _, store = parts
    client.app.state.desktop.busy = True
    assert client.post("/api/settings", json={"api_key": KEY}).status_code == 409
    assert client.delete("/api/settings/key").status_code == 409
    assert store.get() is None


def test_invalid_request_does_not_echo_the_key(parts):
    client, _, _ = parts
    r = client.post("/api/settings", json={"api_key": 5})
    assert r.status_code == 422 and KEY not in r.text


def test_load_and_apply_at_startup(env):
    tmp_path, _, _ = env
    store = MemoryStore()
    store.set(KEY)
    settings = Settings(store, tmp_path / "s.json")
    settings.load_and_apply()
    assert config.current_api_key() == KEY and config.active_provider() == "deepseek"


def test_key_never_reaches_the_log_or_errors(parts, caplog):
    client, _, _ = parts
    client.post("/api/settings", json={"api_key": KEY})
    client.post("/api/client-error", json={"message": f"boom {KEY}", "stack": KEY})
    assert KEY not in caplog.text


def test_test_key_messages(env, monkeypatch):
    from fastapi import HTTPException
    request = httpx.Request("POST", "https://api.deepseek.com/anthropic/v1/messages")

    cases = [(anthropic.AuthenticationError("no", response=httpx.Response(401, request=request), body=None), 401),
             (anthropic.BadRequestError("Your credit balance is too low", response=httpx.Response(400, request=request), body=None), 402),
             (anthropic.APIConnectionError(request=request), 502)]
    for error, code in cases:
        class Messages:
            def create(self, **kw):
                raise error
        monkeypatch.setattr(server, "make_anthropic_client", lambda key, **o: type("C", (), {"messages": Messages()})())
        with pytest.raises(HTTPException) as raised:
            REAL_TEST_KEY(KEY)
        assert raised.value.status_code == code and KEY not in raised.value.detail


def test_the_window_gets_the_page_where_a_key_is_created(parts):
    client, _, _ = parts
    info = client.get("/api/settings").json()
    assert info["keys_url"] == "https://platform.deepseek.com/api_keys"
    assert "providers" not in info and "models" not in info      # one service, one model: nothing to choose
