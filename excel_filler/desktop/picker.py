"""A file dialog for the browser mode on Linux.

The native dialogs of the window (pywebview) do not exist when the app is opened in a browser, and a
browser never gives a web page the full path of a file. The backend runs on the person's own machine
(127.0.0.1), so it opens the system's own dialog, zenity, and returns the paths it gives.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT = 600  # seconds the person has to choose before the dialog is closed
SEPARATOR = "\n"  # zenity's default "|" can be part of a path

TITLES = {"workbook": "Choose the Excel workbook to fill", "documents": "Choose the documents", "folder": "Choose the folder of the documents"}


def available() -> bool:
    """A dialog can be shown: Linux, zenity installed, and a graphical session."""
    return (sys.platform.startswith("linux") and shutil.which("zenity") is not None
            and bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")))


def command(kind: str, start: str | None = None) -> list[str]:
    """The zenity command line for one kind of dialog: workbook (one .xlsx/.xlsm), documents (several
    files) or folder (one folder). start: the folder the dialog opens in, when it exists."""
    if kind not in TITLES:
        raise ValueError(f"Unknown dialog: {kind}")
    cmd = ["zenity", "--file-selection", f"--title={TITLES[kind]}"]
    if kind == "workbook":
        cmd += ["--file-filter=Excel workbooks | *.xlsx *.xlsm", "--file-filter=All files | *"]
    elif kind == "documents":
        cmd += ["--multiple", f"--separator={SEPARATOR}"]
    else:
        cmd += ["--directory"]
    if start:
        folder = Path(start).expanduser()
        if folder.is_dir():
            cmd.append(f"--filename={folder}/")  # the trailing slash makes zenity open IN the folder
    return cmd


def pick(kind: str, start: str | None = None) -> list[str]:
    """Show the dialog and return the chosen paths ([] when the person cancels)."""
    try:
        done = subprocess.run(command(kind, start), capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return []
    if done.returncode == 1:  # zenity: cancelled
        return []
    if done.returncode != 0:
        lines = (done.stderr or "").strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "The file dialog failed.")
    return [p for p in done.stdout.split(SEPARATOR) if p.strip()]
