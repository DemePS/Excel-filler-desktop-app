"""The file dialog of the browser mode (zenity on Linux, tkinter anywhere), without showing any dialog."""

import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from excel_filler.desktop import app as launcher, picker
from excel_filler.desktop.server import create_app

TOKEN = "t0ken"


def test_the_zenity_command_for_each_kind_of_dialog(tmp_path):
    workbook = picker.command("workbook", str(tmp_path))
    assert workbook[:2] == ["zenity", "--file-selection"] and any("*.xlsx" in a for a in workbook)
    assert f"--filename={tmp_path}/" in workbook                                   # opens IN the folder
    docs = picker.command("documents")
    assert "--multiple" in docs and "--separator=\n" in docs and not any(a.startswith("--filename") for a in docs)
    assert "--directory" in picker.command("folder", str(tmp_path / "missing"))     # a folder that does not exist is ignored
    assert not any(a.startswith("--filename") for a in picker.command("folder", str(tmp_path / "missing")))
    with pytest.raises(ValueError):
        picker.command("shell; rm -rf /")


def test_the_tk_command_runs_python_with_the_kind_the_title_and_the_folder(tmp_path):
    cmd = picker.command("documents", str(tmp_path), which="tk")
    assert cmd[0] == sys.executable and cmd[1] == "-c" and cmd[3:] == ["documents", picker.TITLES["documents"], str(tmp_path)]
    assert picker.command("folder", None, which="tk")[-1] == ""                    # no start folder: the dialog's default
    compile(picker.TK_PROGRAM, "tk_program", "exec")                               # the program is valid Python


def test_which_dialog_is_used(monkeypatch):
    monkeypatch.setattr(picker.sys, "frozen", False, raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(picker.sys, "platform", "linux")
    monkeypatch.setattr(picker.shutil, "which", lambda name: "/usr/bin/zenity")
    assert picker.backend() == "zenity"                                            # Linux with zenity
    monkeypatch.setattr(picker.shutil, "which", lambda name: None)
    monkeypatch.setattr(picker.importlib.util, "find_spec", lambda name: object())
    assert picker.backend() == "tk"                                                # Linux without zenity: tkinter
    monkeypatch.setattr(picker.importlib.util, "find_spec", lambda name: None)
    assert picker.backend() is None                                                # no Tk either: the path is typed
    monkeypatch.setattr(picker.importlib.util, "find_spec", lambda name: object())
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert picker.backend() is None                                                # no graphical session
    monkeypatch.setattr(picker.sys, "platform", "win32")
    assert picker.backend() == "tk"                                                # Windows has no DISPLAY and needs none
    monkeypatch.setattr(picker.sys, "frozen", True, raising=False)
    assert picker.backend() is None                                                # the frozen app uses the window's dialogs


def test_paths_are_split_on_new_lines_and_cancel_gives_nothing(monkeypatch):
    def fake(code, out="", err=""):
        return lambda cmd, **kw: subprocess.CompletedProcess(cmd, code, out, err)
    monkeypatch.setattr(picker, "backend", lambda: "zenity")
    monkeypatch.setattr(subprocess, "run", fake(0, "/a/one|two.pdf\n/b/three.pdf\n"))
    assert picker.pick("documents") == ["/a/one|two.pdf", "/b/three.pdf"]          # a "|" in a name is kept
    monkeypatch.setattr(subprocess, "run", fake(1))
    assert picker.pick("workbook") == []                                           # zenity: cancelled
    monkeypatch.setattr(subprocess, "run", fake(255, err="Gtk-WARNING: cannot open display\n"))
    with pytest.raises(RuntimeError, match="cannot open display"):
        picker.pick("folder")
    monkeypatch.setattr(picker, "backend", lambda: "tk")
    monkeypatch.setattr(subprocess, "run", fake(0, "C:/Users/me/costs.xlsx\n"))
    assert picker.pick("workbook") == ["C:/Users/me/costs.xlsx"]                   # a Windows path
    monkeypatch.setattr(subprocess, "run", fake(0, "\n"))
    assert picker.pick("workbook") == []                                           # tk: cancelled prints nothing
    monkeypatch.setattr(picker, "backend", lambda: None)
    with pytest.raises(RuntimeError, match="No file dialog"):
        picker.pick("workbook")


def test_the_routes(monkeypatch):
    client = TestClient(create_app(TOKEN), headers={"x-token": TOKEN})
    monkeypatch.setattr(picker, "backend", lambda: None)
    assert client.get("/api/pick/available").json() == {"available": False}
    assert client.post("/api/pick", json={"kind": "workbook"}).status_code == 501
    monkeypatch.setattr(picker, "backend", lambda: "tk")
    monkeypatch.setattr(picker, "pick", lambda kind, folder=None: [f"/x/{kind}.xlsx", folder or ""])
    assert client.get("/api/pick/available").json() == {"available": True}
    assert client.post("/api/pick", json={"kind": "workbook", "folder": "/tmp"}).json() == {"paths": ["/x/workbook.xlsx", "/tmp"]}
    assert client.post("/api/pick", json={"kind": "nonsense"}).status_code == 400
    assert TestClient(create_app(TOKEN)).post("/api/pick", json={"kind": "workbook"}).status_code == 403   # the token is needed


def test_the_native_window_is_tried_only_where_a_toolkit_exists(monkeypatch):
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    assert launcher.native_window_possible() is True                               # WebView2
    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    assert launcher.native_window_possible() is True
    monkeypatch.setattr(launcher.sys, "platform", "linux")
    monkeypatch.setattr(launcher.importlib.util, "find_spec", lambda name: None)
    assert launcher.native_window_possible() is False                              # no gi, no qtpy: the browser, quietly
    monkeypatch.setattr(launcher.importlib.util, "find_spec", lambda name: object() if name == "gi" else None)
    assert launcher.native_window_possible() is True                               # GTK
