"""Launch the desktop window: start the local backend, then open it in a native window.

    excel-filler-desktop            # native window (WebView2 on Windows)
    excel-filler-desktop --browser  # open in the default browser instead (development)
"""

from __future__ import annotations

import argparse
import secrets
import socket
import threading
import time
import webbrowser

import uvicorn

from coding_agent import session


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WindowApi:
    """Functions the web page can call through pywebview (window.pywebview.api.*)."""

    def __init__(self) -> None:
        self.window = None

    def pick_folder(self) -> str | None:
        import webview
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Excel filler desktop window.")
    parser.add_argument("--browser", action="store_true", help="Open in the default browser instead of a window.")
    args = parser.parse_args()

    from .server import create_app

    token = secrets.token_urlsafe(24)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(token), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, name="backend", daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}/?token={token}"

    try:
        if args.browser:
            webbrowser.open(url)
            print(f"Excel filler is running at {url}  (Ctrl+C to quit)")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        else:
            import webview
            api = WindowApi()
            api.window = webview.create_window("Excel filler", url, js_api=api, width=1280, height=820, min_size=(900, 600))
            webview.start()
    finally:
        session.stop()
        server.should_exit = True
        session.close()
