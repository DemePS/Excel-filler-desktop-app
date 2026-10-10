"""Update chart of accounts: the file of the knowledge folder is replaced, indexed, and a bad file changes nothing."""

import pytest
from fastapi.testclient import TestClient

from coding_agent import index
from excel_filler import agent, chart
from excel_filler.desktop.server import create_app

TOKEN = "t0ken"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCEL_FILLER_KNOWLEDGE", str(tmp_path / "knowledge"))
    monkeypatch.setenv("AGENT_INDEX_DIR", str(tmp_path / "index"))
    monkeypatch.setattr(chart, "DEFAULT_FOLDER", tmp_path / "default")
    return TestClient(create_app(TOKEN), headers={"x-token": TOKEN})


def test_no_chart_yet(client):
    r = client.get("/api/chart-of-accounts").json()
    assert r["file"] is None and r["folder"].endswith("knowledge")


def test_the_chart_is_installed_replaced_and_searchable(client, tmp_path):
    new = tmp_path / "pcg-2026.txt"
    new.write_text("Compte 2183 Matériel de bureau et matériel informatique\n")
    r = client.post("/api/chart-of-accounts", json={"path": str(new)})
    assert r.status_code == 200 and r.json()["file"] == "plan-comptable.txt"
    knowledge = tmp_path / "knowledge"
    assert index.search([knowledge], "matériel informatique")["hits"]          # indexed at once

    csv = tmp_path / "other.md"
    csv.write_text("compte 2184 Mobilier\n")
    assert client.post("/api/chart-of-accounts", json={"path": str(csv)}).json()["file"] == "plan-comptable.md"
    assert [p.name for p in knowledge.iterdir()] == ["plan-comptable.md"]          # one chart: the old one is gone
    assert not index.search([knowledge], "informatique")["hits"]


def test_a_file_that_cannot_be_used_leaves_the_current_chart(client, tmp_path):
    good = tmp_path / "good.txt"
    good.write_text("Compte 606 Achats non stockés\n")
    client.post("/api/chart-of-accounts", json={"path": str(good)})
    for name, content in (("bad.pdf", b"not a pdf"), ("book.xlsx", b"x"), ("data.csv", b"a;b"), ("empty.txt", b"")):
        p = tmp_path / name
        p.write_bytes(content)
        r = client.post("/api/chart-of-accounts", json={"path": str(p)})
        assert r.status_code == 400, name
    assert client.post("/api/chart-of-accounts", json={"path": str(tmp_path / "missing.pdf")}).status_code == 400
    assert client.get("/api/chart-of-accounts").json()["file"] == "plan-comptable.txt"
    assert (tmp_path / "knowledge" / "plan-comptable.txt").read_text().startswith("Compte 606")


def test_without_the_variable_the_default_folder_is_used_once_it_exists(tmp_path, monkeypatch):
    monkeypatch.delenv("EXCEL_FILLER_KNOWLEDGE", raising=False)
    monkeypatch.setattr(chart, "DEFAULT_FOLDER", tmp_path / "default")
    assert agent.knowledge_folder() is None
    (tmp_path / "default").mkdir()
    assert agent.knowledge_folder() == (tmp_path / "default").resolve()
