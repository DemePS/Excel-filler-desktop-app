"""The desktop backend: token protection, and a whole job driven like the window drives it."""

import openpyxl
import pytest
from fastapi.testclient import TestClient

from coding_agent import config, memory, session
from excel_filler.desktop.server import create_app

from .helpers import FakeClaude, make_pdf

TOKEN = "t0ken"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "MEMORY_HOME", tmp_path / "memory-home")
    monkeypatch.setattr(config, "MEMORY_UPDATES", False)
    monkeypatch.setattr(memory, "MEMORY_UPDATES", False)
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_ENDPOINT", "https://x.services.ai.azure.com/anthropic")
    import coding_agent.tools.documents as documents
    monkeypatch.setattr(documents, "BACKUP_HOME", tmp_path / "backups")
    return TestClient(create_app(TOKEN), headers={"x-token": TOKEN})


@pytest.fixture
def folder(tmp_path):
    f = tmp_path / "job"
    f.mkdir()
    make_pdf(f / "invoice.pdf", ["Sensors 12 x 45.50 EUR"])
    wb = openpyxl.Workbook()
    wb.active.title = "Costs"
    wb.active.append(["Item", "Qty"])
    wb.save(f / "costs.xlsx")
    return f


def test_requests_without_the_token_are_refused(client):
    assert client.get("/api/state", headers={"x-token": "wrong"}).status_code == 403
    assert client.get("/api/state", headers={"x-token": TOKEN, "host": "evil.example"}).status_code == 403
    assert client.get("/api/state").status_code == 200


def test_open_folder_lists_workbooks_and_documents(client, folder):
    r = client.post("/api/folder", json={"path": str(folder)})
    assert r.status_code == 200
    assert r.json()["workbooks"] == ["costs.xlsx"] and r.json()["documents"] == ["invoice.pdf"]
    assert client.post("/api/folder", json={"path": str(folder / "nope")}).status_code == 400


def test_a_whole_job_through_the_api(client, folder, monkeypatch):
    fake = FakeClaude([
        ([("read_excel", {"path": "costs.xlsx"})], "tool_use"),
        ([("edit_excel", {"path": "costs.xlsx", "changes": [
            {"sheet": "Costs", "cell": "A2", "value": "Sensors"}, {"sheet": "Costs", "cell": "B2", "value": 12}]})], "tool_use"),
        ([("text", "Filled row 2 from invoice.pdf page 1.")], "end_turn"),
    ])
    monkeypatch.setattr(session, "_get_client", fake.client)
    client.post("/api/folder", json={"path": str(folder)})
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["workbooks"] == ["costs.xlsx"]
        assert client.post("/api/job", json={"workbook": "costs.xlsx", "documents": ["invoice.pdf"]}).json() == {"started": True}
        events = []
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["type"] == "confirm":
                assert event["question"] == "Apply these cell changes to costs.xlsx?"
                assert client.post("/api/job", json={"workbook": "costs.xlsx"}).status_code == 409  # one job at a time
                client.post("/api/answer", json={"id": event["id"], "value": "yes"})
            if event["type"] == "busy" and event["busy"] is False:
                break
    kinds = [e["type"] for e in events]
    assert kinds[0] == "busy" and "cells" in kinds and "success" in kinds
    cells = next(e for e in events if e["type"] == "cells")
    assert {"cell": "Costs!B2", "old": "", "new": "12", "format": None} in cells["rows"]
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert text == "Filled row 2 from invoice.pdf page 1."
    ws_ = openpyxl.load_workbook(folder / "costs.xlsx")["Costs"]
    assert (ws_["A2"].value, ws_["B2"].value) == ("Sensors", 12)


def test_stop_answers_pending_questions_negatively(client, folder, monkeypatch):
    fake = FakeClaude([
        ([("edit_excel", {"path": "costs.xlsx", "changes": [{"cell": "A2", "value": "x"}]})], "tool_use"),
        ([("text", "never")], "end_turn"),
    ])
    monkeypatch.setattr(session, "_get_client", fake.client)
    client.post("/api/folder", json={"path": str(folder)})
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_json()
        client.post("/api/job", json={"workbook": "costs.xlsx"})
        while (event := ws.receive_json())["type"] != "confirm":
            pass
        client.post("/api/stop")
        while not ((event := ws.receive_json())["type"] == "busy" and event["busy"] is False):
            pass
    assert openpyxl.load_workbook(folder / "costs.xlsx")["Costs"]["A2"].value is None


def test_the_real_server_accepts_the_window_websocket():
    """Through uvicorn itself (the test client above bypasses it): the WebSocket must work."""
    import asyncio
    import json
    import socket
    import threading
    import time

    import uvicorn
    import websockets

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(TOKEN), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.02)

    async def hello():
        async with websockets.connect(f"ws://127.0.0.1:{port}/ws?token={TOKEN}") as ws:
            return json.loads(await ws.recv())

    try:
        assert asyncio.run(hello())["type"] == "hello"
    finally:
        server.should_exit = True


def test_the_launcher_imports_without_a_console(tmp_path):
    """Started as a windowed app on Windows, sys.stdout/stderr are None: importing must not crash."""
    import subprocess
    import sys
    marker = tmp_path / "ok"
    code = ("import sys; sys.stdout = sys.stderr = None\n"
            "import excel_filler.desktop.app, excel_filler.desktop.server\n"
            "open(sys.argv[1], 'w').write('ok')")
    subprocess.run([sys.executable, "-c", code, str(marker)], check=True)
    assert marker.read_text() == "ok"
