"""Launch the desktop window: start the local backend, then open it in a native window.

    excel-filler-desktop            # native window (WebView2 on Windows); falls back to the browser
    excel-filler-desktop --browser  # open in the default browser instead

Everything (startup, errors, the backend's log) also goes to
~/.coding-agent/logs/excel-filler-desktop.log, so a failure is never silent.
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

# Settings: a .env in the current folder, or ~/.coding-agent/.env (read before the agent package,
# which reads its configuration when imported).
HOME = Path(os.environ["HOME"]).expanduser() if os.environ.get("HOME") else Path.home()
load_dotenv()
load_dotenv(HOME / ".coding-agent" / ".env")

LOG_FILE = HOME / ".coding-agent" / "logs" / "excel-filler-desktop.log"
log = logging.getLogger("excel-filler")


def setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    else:  # no console (started as a windowed app): send stray output to the log file too
        sys.stdout = sys.stderr = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    # Libraries: only their errors. Azure's sign-in chatter and one line per HTTP request add nothing;
    # the job log (excel-filler.job) says what the agent does.
    logging.getLogger("azure").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    def excepthook(kind, value, tb):
        log.error("Unexpected error:\n%s", "".join(traceback.format_exception(kind, value, tb)))
    sys.excepthook = excepthook
    threading.excepthook = lambda args: excepthook(args.exc_type, args.exc_value, args.exc_traceback)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WindowApi:
    """Functions the web page can call through pywebview (window.pywebview.api.*).

    pywebview exposes every public attribute of this object to the page, walking into it
    recursively; keep the window (a native .NET object) private, or it walks the whole native
    window and fails ("maximum recursion depth", "only accessed from the UI thread").
    """

    def __init__(self) -> None:
        self._window = None

    def pick_workbook(self) -> str | None:
        """A Windows "Open" dialog showing Excel files (a folder dialog would not show the files)."""
        result = self._window.create_file_dialog(
            open_dialog(), file_types=("Excel workbooks (*.xlsx;*.xlsm)", "All files (*.*)"))
        return result[0] if result else None

    def pick_documents(self, folder: str) -> list[str]:
        """An "Open" dialog in the workbook's folder; several PDFs or images can be selected."""
        result = self._window.create_file_dialog(
            open_dialog(), directory=folder, allow_multiple=True,
            file_types=("Documents (*.pdf;*.png;*.jpg;*.jpeg;*.webp)", "All files (*.*)"))
        return list(result or [])

    def pick_document_folder(self, folder: str) -> str | None:
        """A folder dialog, for the folder holding the documents (it shows folders only)."""
        result = self._window.create_file_dialog(folder_dialog(), directory=folder)
        return (result[0] if isinstance(result, (list, tuple)) else result) or None


def folder_dialog():
    import webview
    return webview.FileDialog.FOLDER if hasattr(webview, "FileDialog") else webview.FOLDER_DIALOG


def open_dialog():
    import webview
    return webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else webview.OPEN_DIALOG


def run_in_browser(url: str) -> None:
    webbrowser.open(url)
    print(f"Excel filler is running at:\n  {url}\nKeep this window open; press Ctrl+C to quit.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def run_in_window(url: str) -> None:
    import webview
    api = WindowApi()
    api._window = webview.create_window("Excel filler", url, js_api=api, width=1280, height=820, min_size=(900, 600))
    webview.start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Excel filler desktop window.")
    parser.add_argument("--browser", action="store_true", help="Open in the default browser instead of a window.")
    args = parser.parse_args()
    setup_logging()
    log.info("Starting (Python %s, %s); log file: %s", sys.version.split()[0], sys.platform, LOG_FILE)

    import uvicorn

    from coding_agent import session

    from .server import create_app

    token = secrets.token_urlsafe(24)
    port = free_port()
    config = uvicorn.Config(create_app(token), host="127.0.0.1", port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, name="backend", daemon=True).start()
    deadline = time.time() + 20
    while not server.started:
        if time.time() > deadline:
            log.error("The local backend did not start within 20 s (see the errors above).")
            raise SystemExit(1)
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}/?token={token}"
    log.info("Backend ready on 127.0.0.1:%s", port)
    from coding_agent.errors import connection_summary
    log.info("Claude: %s", connection_summary())

    try:
        if args.browser:
            run_in_browser(url)
        else:
            try:
                run_in_window(url)
            except Exception as e:  # no WebView2 runtime, .NET problem, no GUI toolkit...
                log.warning("The native window could not open (%s: %s); using the browser instead.", type(e).__name__, e)
                run_in_browser(url)
    finally:
        session.stop()
        server.should_exit = True
        session.close()
        log.info("Stopped.")
