"""The organization's gateway: its settings at startup, the saved copy, the minimum version."""

import json

import pytest
from fastapi.testclient import TestClient

from excel_filler import gateway

KEYS = ["EXCEL_FILLER_GATEWAY", "EXCEL_FILLER_API_SCOPE", "EXCEL_FILLER_CLIENT_ID", "ANTHROPIC_FOUNDRY_ENDPOINT",
        "ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_DEPLOYMENT", "TOKEN_SCOPE", "ANTHROPIC_FOUNDRY_CLIENT_ID",
        "EXCEL_FILLER_TENANT_ID", "AZURE_TENANT_ID"]
URL = "https://apim.example/excel-filler"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(gateway, "_current", gateway.Gateway())
    monkeypatch.setattr(gateway, "app_version", lambda: "0.1.0")


def serve(monkeypatch, settings=None, error=None):
    calls = []

    def fetch(url, headers, timeout=10.0):
        calls.append((url, headers))
        if error:
            raise error
        return settings
    monkeypatch.setattr(gateway, "fetch_settings", fetch)
    return calls


def test_without_a_gateway_nothing_changes(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_ENDPOINT", "https://res.services.ai.azure.com/anthropic")
    g = gateway.configure(tmp_path)
    assert g.url is None and os.environ["ANTHROPIC_FOUNDRY_ENDPOINT"].startswith("https://res.")


def test_the_gateway_becomes_the_endpoint_and_its_settings_apply(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("EXCEL_FILLER_GATEWAY", URL + "/")
    monkeypatch.setenv("EXCEL_FILLER_API_SCOPE", "api://gw/.default")
    monkeypatch.setenv("EXCEL_FILLER_CLIENT_ID", "desktop-app")
    monkeypatch.setenv("EXCEL_FILLER_TENANT_ID", "corp-tenant")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "a-key-left-on-the-pc")
    calls = serve(monkeypatch, {"deployment": "claude-sonnet-prod", "minimum_version": "0.1.0", "notice": "Maintenance Friday"})
    g = gateway.configure(tmp_path)
    assert calls[0][0] == URL and calls[0][1]["x-app-version"] == "0.1.0"
    assert (g.source, g.deployment, g.notice, g.update_required) == ("gateway", "claude-sonnet-prod", "Maintenance Friday", None)
    assert os.environ["ANTHROPIC_FOUNDRY_ENDPOINT"] == URL
    assert os.environ["ANTHROPIC_FOUNDRY_DEPLOYMENT"] == "claude-sonnet-prod"
    assert os.environ["TOKEN_SCOPE"] == "api://gw/.default" and os.environ["ANTHROPIC_FOUNDRY_CLIENT_ID"] == "desktop-app"
    assert os.environ["AZURE_TENANT_ID"] == "corp-tenant"
    assert "ANTHROPIC_FOUNDRY_API_KEY" not in os.environ  # through the gateway: sign-in only
    saved = json.loads((tmp_path / ".coding-agent" / gateway.SETTINGS_FILE_NAME).read_text())
    assert saved["deployment"] == "claude-sonnet-prod" and saved["url"] == URL


def test_the_last_settings_are_used_when_the_gateway_does_not_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCEL_FILLER_GATEWAY", URL)
    serve(monkeypatch, {"deployment": "claude-a"})
    gateway.configure(tmp_path)
    serve(monkeypatch, error=OSError("timed out"))
    g = gateway.configure(tmp_path)
    assert (g.source, g.deployment) == ("saved", "claude-a") and "timed out" in g.problem
    assert "last ones read" in gateway.describe(g)


def test_never_read_settings_leave_the_default_deployment(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("EXCEL_FILLER_GATEWAY", URL)
    serve(monkeypatch, error=OSError("unreachable"))
    g = gateway.configure(tmp_path)
    assert g.source == "none" and g.deployment is None and os.environ["ANTHROPIC_FOUNDRY_ENDPOINT"] == URL
    assert "ANTHROPIC_FOUNDRY_DEPLOYMENT" not in os.environ


def test_an_older_version_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCEL_FILLER_GATEWAY", URL)
    serve(monkeypatch, {"minimum_version": "0.10.0"})
    g = gateway.configure(tmp_path)
    assert "0.10.0 or later is required" in g.update_required
    assert gateway.version_tuple("0.9.9") < gateway.version_tuple("0.10.0")


def test_the_window_shows_the_notice_and_refuses_jobs_when_an_update_is_required(tmp_path, monkeypatch):
    from excel_filler.desktop.server import create_app
    monkeypatch.setenv("EXCEL_FILLER_GATEWAY", URL)
    serve(monkeypatch, {"minimum_version": "9.0", "notice": "Please update"})
    gateway.configure(tmp_path)
    client = TestClient(create_app("t"), headers={"x-token": "t"})
    state = client.get("/api/state").json()
    assert state["notice"] == "Please update" and "9.0 or later is required" in state["connection_problem"]
    assert client.get("/api/check").json()["ok"] is False
    (tmp_path / "job").mkdir()
    client.post("/api/folder", json={"path": str(tmp_path / "job")})
    r = client.post("/api/job", json={"workbook": "x.xlsx", "documents": []})
    assert r.status_code == 400 and "9.0 or later" in r.json()["detail"]


def test_the_app_name_and_version_go_with_every_request(tmp_path, monkeypatch):
    from coding_agent import config
    monkeypatch.setattr(config, "CLIENT_HEADERS", {})
    gateway.configure(tmp_path)
    gateway.apply_headers()
    assert config.CLIENT_HEADERS == {"x-app-name": "excel-filler", "x-app-version": "0.1.0"}
