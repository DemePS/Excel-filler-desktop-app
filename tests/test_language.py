"""The window's language: the agent writes its summary and questions in French when the window is in French."""

import pytest
from fastapi.testclient import TestClient

from coding_agent import backups, config, memory, session
from excel_filler import agent
from excel_filler.desktop.server import create_app

from .helpers import FakeClaude, make_pdf

TOKEN = "t0ken"


def test_the_hint_is_only_for_french():
    assert agent.language_hint("fr") == "Write your summary, your questions and your remarks in French. Keep the workbook's values and headers as they are."
    assert agent.language_hint("FR") == agent.language_hint("fr")
    assert agent.language_hint("en") == "" and agent.language_hint("") == "" and agent.language_hint("de") == ""   # English: unchanged


def test_the_job_instruction_carries_the_language_after_the_person_s_notes():
    plain = agent.job_instruction("costs.xlsx", ["a.pdf"], notes="amounts in EUR")
    assert agent.job_instruction("costs.xlsx", ["a.pdf"], notes="amounts in EUR", language="en") == plain       # nothing added
    french = agent.job_instruction("costs.xlsx", ["a.pdf"], notes="amounts in EUR", language="fr")
    assert french.startswith(plain) and french.rstrip().endswith("headers as they are.") and "in French" in french


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "MEMORY_HOME", tmp_path / "memory-home")
    monkeypatch.setattr(config, "MEMORY_UPDATES", False)
    monkeypatch.setattr(memory, "MEMORY_UPDATES", False)
    monkeypatch.setattr(backups, "BACKUP_HOME", tmp_path / "backups")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_ENDPOINT", "https://x.services.ai.azure.com/anthropic")
    import openpyxl
    folder = tmp_path / "job"
    folder.mkdir()
    make_pdf(folder / "invoice.pdf", ["Sensors 12 x 45.50 EUR"])
    wb = openpyxl.Workbook()
    wb.active.title = "Costs"
    wb.active.append(["Item", "Qty"])
    wb.save(folder / "costs.xlsx")
    return TestClient(create_app(TOKEN), headers={"x-token": TOKEN}), folder


def run(client, folder, monkeypatch, body, follow_up=None):
    fake = FakeClaude([([("text", "Done.")], "end_turn"), ([("text", "Corrected.")], "end_turn")])
    monkeypatch.setattr(session, "_get_client", fake.client)
    client.post("/api/folder", json={"path": str(folder)})
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_json()

        def wait():
            while True:
                event = ws.receive_json()
                if event["type"] == "busy" and event["busy"] is False:
                    return
        assert client.post("/api/job", json=body).json()["started"] is True
        wait()
        if follow_up:
            assert client.post("/api/followup", json=follow_up).json() == {"started": True}
            wait()
    return fake


def last_text(request):
    content = request["messages"][-1]["content"]
    return content if isinstance(content, str) else " ".join(b.get("text", "") for b in content if isinstance(b, dict))


def test_a_french_job_and_follow_up_ask_the_agent_to_answer_in_french(client, monkeypatch):
    c, folder = client
    fake = run(c, folder, monkeypatch, {"workbook": "costs.xlsx", "documents": ["invoice.pdf"], "language": "fr"},
               {"text": "la date est fausse ligne 2", "language": "fr"})
    assert "in French" in last_text(fake.requests[0])
    assert last_text(fake.requests[1]).startswith("la date est fausse ligne 2") and "in French" in last_text(fake.requests[1])


def test_an_english_job_is_unchanged(client, monkeypatch):
    c, folder = client
    fake = run(c, folder, monkeypatch, {"workbook": "costs.xlsx", "documents": ["invoice.pdf"], "language": "en"},
               {"text": "the date is wrong in row 2", "language": "en"})
    assert "French" not in last_text(fake.requests[0]) and "French" not in last_text(fake.requests[1])
