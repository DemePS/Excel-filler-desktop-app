"""A file dialog for the browser mode, on Windows and Linux.

The native dialogs of the window (pywebview) do not exist when the app is opened in a browser, and a
browser never gives a web page the full path of a file. The backend runs on the person's own machine
(127.0.0.1), so it opens the system's dialog itself, in a separate process, and returns the paths:

* zenity, on Linux when it is installed (the GTK dialog of the desktop);
* tkinter's dialogs, on any system where Python has Tk (Windows always does).

When neither exists the window asks for the path to be typed.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT = 600  # seconds the person has to choose before the dialog is closed
SEPARATOR = "\n"  # zenity's default "|" can be part of a path

TITLES = {"workbook": "Choose the Excel workbook to fill", "documents": "Choose the documents", "folder": "Choose the folder of the documents",
          "chart": "Choose the chart of accounts (PDF or text)"}

# The tkinter dialog, as a program for `python -c`: argv = kind, title, start folder. One path per line.
TK_PROGRAM = """
import sys
import tkinter
from tkinter import filedialog
kind, title, start = sys.argv[1:4]
root = tkinter.Tk()
root.withdraw()
try:
    root.attributes("-topmost", True)  # the dialog comes in front of the browser
except Exception:
    pass
options = {"title": title, "parent": root}
if start:
    options["initialdir"] = start
if kind == "workbook":
    chosen = [filedialog.askopenfilename(filetypes=[("Excel workbooks", "*.xlsx *.xlsm"), ("All files", "*")], **options)]
elif kind == "chart":
    chosen = [filedialog.askopenfilename(filetypes=[("Chart of accounts", "*.pdf *.txt *.md"), ("All files", "*")], **options)]
elif kind == "documents":
    chosen = list(filedialog.askopenfilenames(**options))
else:
    chosen = [filedialog.askdirectory(**options)]
print("\\n".join(p for p in chosen if p))
"""


def backend() -> str | None:
    """Which dialog can be shown here: "zenity", "tk", or None (the person types the path)."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or sys.platform in ("win32", "darwin")):
        return None  # no graphical session
    if sys.platform.startswith("linux") and shutil.which("zenity") is not None:
        return "zenity"
    if getattr(sys, "frozen", False):
        return None  # the frozen app has no `python -c`; in its window the native dialogs are used
    if importlib.util.find_spec("tkinter") is not None:
        return "tk"
    return None


def available() -> bool:
    return backend() is not None


def _start(start: str | None) -> str:
    if start:
        folder = Path(start).expanduser()
        if folder.is_dir():
            return str(folder)
    return ""


def command(kind: str, start: str | None = None, which: str = "zenity") -> list[str]:
    """The command line that shows one kind of dialog: workbook (one .xlsx/.xlsm), documents (several
    files) or folder (one folder). start: the folder the dialog opens in, when it exists."""
    if kind not in TITLES:
        raise ValueError(f"Unknown dialog: {kind}")
    folder = _start(start)
    if which == "tk":
        return [sys.executable, "-c", TK_PROGRAM, kind, TITLES[kind], folder]
    cmd = ["zenity", "--file-selection", f"--title={TITLES[kind]}"]
    if kind == "workbook":
        cmd += ["--file-filter=Excel workbooks | *.xlsx *.xlsm", "--file-filter=All files | *"]
    elif kind == "chart":
        cmd += ["--file-filter=Chart of accounts | *.pdf *.txt *.md", "--file-filter=All files | *"]
    elif kind == "documents":
        cmd += ["--multiple", f"--separator={SEPARATOR}"]
    else:
        cmd += ["--directory"]
    if folder:
        cmd.append(f"--filename={folder}/")  # the trailing slash makes zenity open IN the folder
    return cmd


def pick(kind: str, start: str | None = None) -> list[str]:
    """Show the dialog and return the chosen paths ([] when the person cancels)."""
    which = backend()
    if which is None:
        raise RuntimeError("No file dialog is available on this system.")
    try:
        done = subprocess.run(command(kind, start, which), capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return []
    if done.returncode == 1 and which == "zenity":  # zenity: cancelled
        return []
    if done.returncode != 0:
        lines = (done.stderr or "").strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "The file dialog failed.")
    return [p.strip() for p in done.stdout.split(SEPARATOR) if p.strip()]
