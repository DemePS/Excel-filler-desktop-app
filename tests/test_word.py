"""Word (.docx) documents: listed, read with read_word, and used by a whole job."""

import zipfile

import openpyxl
import pytest
from fastapi.testclient import TestClient

from coding_agent import backups, config, memory, session, state
from coding_agent.common import ToolError
from excel_filler import agent, office_tools
from excel_filler.desktop.server import create_app

from .helpers import FakeClaude

TOKEN = "t0ken"
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def make_docx(path, paragraphs, table=None):
    p = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in paragraphs)
    rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in row) + "</w:tr>" for row in (table or []))
    body = p + (f"<w:tbl>{rows}</w:tbl>" if table else "")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {W}><w:body>{body}</w:body></w:document>')


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "MEMORY_HOME", tmp_path / "memory-home")
    monkeypatch.setattr(config, "MEMORY_UPDATES", False)
    monkeypatch.setattr(memory, "MEMORY_UPDATES", False)
    monkeypatch.setattr(backups, "BACKUP_HOME", tmp_path / "backups")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_ENDPOINT", "https://x.services.ai.azure.com/anthropic")
    folder = tmp_path / "job"
    folder.mkdir()
    make_docx(folder / "facture.docx", ["Facture n° W-2026-17", "Fournisseur : Atelier du Rhône"],
              table=[["Désignation", "Qté", "PU HT"], ["Câble réseau 20 m", "4", "11,50"]])
    wb = openpyxl.Workbook()
    wb.active.title = "Costs"
    wb.active.append(["Item", "Qty"])
    wb.save(folder / "costs.xlsx")
    return TestClient(create_app(TOKEN), headers={"x-token": TOKEN}), folder


def test_read_word_gives_the_paragraphs_and_the_rows_of_the_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "workspace", tmp_path)
    monkeypatch.setattr(state, "cwd", tmp_path)
    make_docx(tmp_path / "a.docx", ["Facture n° 12", "Total TTC 68,40 €"], table=[["Qté", "PU"], ["10", "4,20"]])
    text = office_tools.read_word("a.docx")
    assert text.splitlines() == ["Facture n° 12", "Total TTC 68,40 €", "Qté | PU", "10 | 4,20"]


def test_read_word_refuses_what_is_not_a_readable_docx(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "workspace", tmp_path)
    monkeypatch.setattr(state, "cwd", tmp_path)
    (tmp_path / "old.doc").write_bytes(b"x")
    (tmp_path / "fake.docx").write_bytes(b"not a zip")
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    for name, message in (("old.doc", "old .doc"), ("fake.docx", "not a valid .docx"), ("a.pdf", "not a .docx"), ("missing.docx", "File not found")):
        with pytest.raises(ToolError, match=message):
            office_tools.read_word(name)


def test_a_docx_is_listed_as_a_document_and_the_tool_is_offered(world):
    client, folder = world
    assert "facture.docx" in client.post("/api/folder", json={"path": str(folder)}).json()["documents"]
    assert "read_word" in agent.TOOLS


def test_a_job_reads_a_word_document(world, monkeypatch):
    client, folder = world
    fake = FakeClaude([
        ([("read_excel", {"path": "costs.xlsx"})], "tool_use"),
        ([("read_word", {"path": "facture.docx"})], "tool_use"),
        ([("edit_excel", {"path": "costs.xlsx", "changes": [{"sheet": "Costs", "cell": "A2", "value": "Câble réseau 20 m"},
                                                               {"sheet": "Costs", "cell": "B2", "value": 4}]})], "tool_use"),
        ([("text", "Filled from facture.docx.")], "end_turn"),
    ])
    monkeypatch.setattr(session, "_get_client", fake.client)
    client.post("/api/folder", json={"path": str(folder)})
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_json()
        assert client.post("/api/job", json={"workbook": "costs.xlsx", "documents": ["facture.docx"]}).json()["started"] is True
        while True:
            event = ws.receive_json()
            if event["type"] == "confirm":
                client.post("/api/answer", json={"id": event["id"], "value": "yes"})
            if event["type"] == "busy" and event["busy"] is False:
                break
    result = fake.tool_results(2)["read"]["content"]
    assert "W-2026-17" in str(result) and "Câble réseau 20 m | 4 | 11,50" in str(result)    # the agent received the document's text
    assert openpyxl.load_workbook(folder / "costs.xlsx")["Costs"]["B2"].value == 4
