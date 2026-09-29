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


# --- Access: is the signed-in person an authorized Excel filler user? (decided by Entra ID)

def token_for(name, roles=None):
    import base64
    claims = {"name": name, **({"roles": roles} if roles is not None else {})}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


@pytest.fixture
def organization(tmp_path, monkeypatch):
    """The downloadable app: the organization's app registration is set."""
    monkeypatch.setenv("EXCEL_FILLER_CLIENT_ID", "desktop-app")
    monkeypatch.setenv("EXCEL_FILLER_API_SCOPE", "api://excel-filler/.default")
    gateway.configure(tmp_path)
    return monkeypatch


def sign_in_as(monkeypatch, token=None, error=None):
    from coding_agent import signin
    scopes = []

    def access_token(scope=None):
        scopes.append(scope)
        if error:
            raise error
        return token
    monkeypatch.setattr(signin, "access_token", access_token)
    return scopes


def test_a_member_of_the_group_is_allowed(organization):
    import os
    scopes = sign_in_as(organization, token_for("Ada Lovelace", ["Excel.Filler.User"]))
    access = gateway.check_access()
    assert (access.state, access.user, access.ok) == ("allowed", "Ada Lovelace", True)
    assert scopes == ["api://excel-filler/.default"]  # a token for the organization's registration
    assert os.environ["ANTHROPIC_FOUNDRY_CLIENT_ID"] == "desktop-app"  # the sign-in uses it, gateway or not


def test_a_token_without_the_role_is_refused(organization):
    sign_in_as(organization, token_for("Bob", []))
    access = gateway.check_access()
    assert (access.state, access.user) == ("denied", "Bob") and "Excel filler users group" in access.message


def test_a_person_not_assigned_is_refused_by_entra_id(organization):
    from azure.core.exceptions import ClientAuthenticationError
    sign_in_as(organization, error=ClientAuthenticationError(
        "AADSTS50105: Your administrator has configured the application to block users unless they are "
        "specifically granted ('assigned') access to the application."))
    access = gateway.check_access()
    assert access.state == "denied" and "not assigned to Excel filler" in access.message


def test_a_failed_sign_in_is_reported(organization):
    from azure.core.exceptions import ClientAuthenticationError
    sign_in_as(organization, error=ClientAuthenticationError("User cancelled"))
    access = gateway.check_access()
    assert access.state == "signin_failed" and "User cancelled" in access.message


def test_developers_have_no_access_check(tmp_path, monkeypatch):
    gateway.configure(tmp_path)  # no organization app registration, no gateway
    scopes = sign_in_as(monkeypatch, token_for("Dev"))
    assert gateway.check_access().state == "not_required" and gateway.check_access().ok
    assert scopes == []  # no sign-in for a check: Foundry is called with your own credential


def test_the_window_waits_for_access_before_any_job(tmp_path, organization):
    from excel_filler.desktop.server import create_app
    results = [gateway.Access("denied", "Ada Lovelace", "Ask IT."), gateway.Access("allowed", "Ada Lovelace")]
    calls = []
    organization.setattr(gateway, "check_access", lambda: calls.append(1) or results[len(calls) - 1])
    organization.setenv("ANTHROPIC_FOUNDRY_ENDPOINT", "https://res.services.ai.azure.com/anthropic")
    client = TestClient(create_app("t"), headers={"x-token": "t"})
    (tmp_path / "job").mkdir()
    client.post("/api/folder", json={"path": str(tmp_path / "job")})
    assert client.post("/api/job", json={"workbook": "x.xlsx", "documents": []}).status_code == 403  # not checked yet
    assert client.get("/api/access").json() == {"state": "denied", "ok": False, "user": "Ada Lovelace", "message": "Ask IT."}
    assert client.get("/api/access").json()["state"] == "denied" and len(calls) == 1  # checked once
    r = client.post("/api/job", json={"workbook": "x.xlsx", "documents": []})
    assert r.status_code == 403 and r.json()["detail"] == "Ask IT."
    assert client.get("/api/access?retry=true").json()["state"] == "allowed" and len(calls) == 2


def test_a_refusal_by_the_gateway_during_a_job_closes_access(tmp_path, organization):
    from excel_filler.desktop.server import Desktop, create_app
    organization.setenv("EXCEL_FILLER_GATEWAY", URL)
    serve(organization, {"deployment": "claude-x"})
    gateway.configure(tmp_path)
    organization.setattr(gateway, "check_access", lambda: gateway.Access("allowed", "Ada Lovelace"))
    desktop = Desktop()
    client = TestClient(create_app("t", desktop), headers={"x-token": "t"})
    assert client.get("/api/access").json()["ok"] is True
    with client.websocket_connect("/ws?token=t") as ws:
        ws.receive_json()
        desktop.ui.error("Access denied by https://apim.example/excel-filler (HTTP 403): you are signed in, but ...")
        events = {ws.receive_json()["type"]: None for _ in range(2)}
    assert set(events) == {"error", "access"}
    assert client.get("/api/access").json()["state"] == "denied"


def test_the_organization_settings_are_built_in(tmp_path, monkeypatch):
    import os
    file = tmp_path / "organization.json"
    file.write_text(json.dumps({"gateway": URL, "api_scope": "api://gw/.default", "client_id": "desktop", "tenant_id": ""}))
    monkeypatch.setenv("EXCEL_FILLER_CLIENT_ID", "set-by-it")
    gateway.organization_defaults(file)
    assert os.environ["EXCEL_FILLER_GATEWAY"] == URL and os.environ["EXCEL_FILLER_API_SCOPE"] == "api://gw/.default"
    assert os.environ["EXCEL_FILLER_CLIENT_ID"] == "set-by-it"  # the environment wins
    assert "EXCEL_FILLER_TENANT_ID" not in os.environ  # empty: not set
