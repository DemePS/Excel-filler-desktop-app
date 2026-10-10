"""The knowledge folder: reference texts the agent searches and reads, never documents to fill from."""

import openpyxl
import pytest
from fastapi.testclient import TestClient

from coding_agent import backups, config, memory, session, state
from excel_filler import agent
from excel_filler.desktop.server import create_app
from excel_filler.desktop.settings import MemoryStore, Settings

from .helpers import FakeClaude, make_pdf

TOKEN = "t0ken"


@pytest.fixture
def world(tmp_path, monkeypatch):
    import coding_agent.index as index
    monkeypatch.setattr(session, "MEMORY_HOME", tmp_path / "memory-home")
    monkeypatch.setattr(config, "MEMORY_UPDATES", False)
    monkeypatch.setattr(memory, "MEMORY_UPDATES", False)
    monkeypatch.setattr(backups, "BACKUP_HOME", tmp_path / "backups")
    monkeypatch.setattr(index, "INDEX_HOME", tmp_path / "index")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_ENDPOINT", "https://x.services.ai.azure.com/anthropic")
    monkeypatch.delenv("EXCEL_FILLER_KNOWLEDGE", raising=False)
    job = tmp_path / "job"
    job.mkdir()
    make_pdf(job / "invoice.pdf", ["Ordinateur portable 1450.00 EUR HT"])
    wb = openpyxl.Workbook()
    wb.active.title = "Journal"
    wb.active.append(["Fournisseur", "HT", "Compte"])
    wb.save(job / "journal.xlsx")
    knowledge = tmp_path / "base"
    knowledge.mkdir()
    make_pdf(knowledge / "pcg.pdf", ["Plan comptable general", "44562 TVA sur immobilisations", "2183 Materiel de bureau et materiel informatique"])
    settings = Settings(MemoryStore(), tmp_path / "settings.json")
    client = TestClient(create_app(TOKEN, settings=settings), headers={"x-token": TOKEN})
    return client, settings, job, knowledge


def test_the_environment_variable_gives_the_folder_read_only(world, monkeypatch):
    client, settings, job, knowledge = world
    listing = client.post("/api/folder", json={"path": str(job)}).json()
    assert knowledge.resolve() not in state.read_roots                                      # nothing set: nothing granted
    monkeypatch.setenv("EXCEL_FILLER_KNOWLEDGE", str(knowledge))
    client.post("/api/folder", json={"path": str(job)})
    assert knowledge.resolve() in state.read_roots                                           # read when a folder is opened


def test_a_folder_that_does_not_exist_is_ignored(world, monkeypatch, tmp_path):
    client, settings, job, knowledge = world
    monkeypatch.setenv("EXCEL_FILLER_KNOWLEDGE", str(tmp_path / "nope"))
    assert client.post("/api/folder", json={"path": str(job)}).status_code == 200


def test_the_agent_can_read_it_but_it_is_never_listed_as_a_document(world, monkeypatch):
    client, settings, job, knowledge = world
    monkeypatch.setenv("EXCEL_FILLER_KNOWLEDGE", str(knowledge))
    listing = client.post("/api/folder", json={"path": str(job)}).json()
    assert listing["documents"] == ["invoice.pdf"] and "pcg.pdf" not in str(listing)        # only the invoice to fill from
    assert knowledge.resolve() in state.read_roots                                           # readable (never writable)
    assert state.workspace == job.resolve()
    client.post("/api/folder", json={"path": str(job)})                                     # opening again resets the folders...
    assert knowledge.resolve() in state.read_roots                                           # ...and grants it again


def test_the_agent_finds_an_account_in_it_with_search_library(world, monkeypatch):
    client, settings, job, knowledge = world
    monkeypatch.setenv("EXCEL_FILLER_KNOWLEDGE", str(knowledge))
    fake = FakeClaude([
        ([("search_library", {"query": "TVA sur immobilisations"})], "tool_use"),
        ([("text", "The account is 44562.")], "end_turn"),
    ])
    monkeypatch.setattr(session, "_get_client", fake.client)
    client.post("/api/folder", json={"path": str(job)})
    assert session.send("Which account is the VAT on fixed assets?")
    result = fake.tool_results(1)["search"]["content"]
    text = result if isinstance(result, str) else " ".join(b.get("text", "") for b in result)
    assert "pcg.pdf" in text and "44562" in text                                             # found in the knowledge folder


def test_the_tools_and_the_prompt_carry_the_accounting_rules():
    assert "search_library" in agent.TOOLS
    prompt = agent.SYSTEM_PROMPT.format(workspace="/job")                                    # no stray braces
    assert "Never write an account number from memory" in prompt and "never fill the workbook from them" in prompt
