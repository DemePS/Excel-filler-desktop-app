"""The local backend of the desktop window: a FastAPI app bound to 127.0.0.1.

The agent runs in a worker thread (one job at a time); its UI calls reach the window as WebSocket
events, and the window answers approvals and questions with POST /api/answer. Every request must
carry the per-launch token (a web page in a browser cannot guess it), so nothing else on the
machine can drive the agent.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coding_agent import session

from .. import agent
from .webui import WebUI

STATIC_DIR = Path(__file__).parent / "static"
DOCUMENT_TYPES = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".txt", ".csv")


class Desktop:
    """The state of the window's single agent session."""

    def __init__(self) -> None:
        self.ui = WebUI()
        self.folder: Path | None = None
        self.workbook: str | None = None  # the workbook the person opened, preselected in the window
        self.extra_documents: set[str] = set()  # documents added from subfolders, relative paths
        self.busy = False
        self.lock = threading.Lock()

    def listing(self) -> dict:
        if self.folder is None:
            return {"folder": None, "workbooks": [], "documents": [], "workbook": None}
        files = sorted((p for p in self.folder.iterdir() if p.is_file()), key=lambda p: p.name.lower())
        documents = [p.name for p in files if p.suffix.lower() in DOCUMENT_TYPES]
        documents += sorted(d for d in self.extra_documents if d not in documents and (self.folder / d).is_file())
        return {
            "folder": str(self.folder),
            "workbooks": [p.name for p in files if p.suffix.lower() in (".xlsx", ".xlsm") and not p.name.startswith("~$")],
            "documents": documents,
            "workbook": self.workbook,
        }

    def open(self, folder: Path, workbook: str | None = None) -> None:
        if self.busy:
            raise HTTPException(409, "Wait for the current job to finish.")
        try:
            self.folder = agent.open_folder(folder, self.ui)
        except (NotADirectoryError, OSError) as e:
            raise HTTPException(400, str(e))
        self.workbook = workbook
        self.extra_documents = set()
        self.ui.emit({"type": "listing", **self.listing()})

    def run(self, job) -> None:
        """Run a job (a function calling the agent) in a worker thread."""
        with self.lock:
            if self.busy:
                raise HTTPException(409, "A job is already running.")
            self.busy = True
        self.ui.new_job()
        self.ui.emit({"type": "busy", "busy": True})

        def worker():
            try:
                job()
            except Exception as e:  # never let the worker die silently
                self.ui.message(f"[error] {type(e).__name__}: {e}")
            finally:
                with self.lock:
                    self.busy = False
                self.ui.emit({"type": "busy", "busy": False})
                self.ui.emit({"type": "listing", **self.listing()})  # the workbook may have changed

        threading.Thread(target=worker, name="agent-job", daemon=True).start()


class FolderIn(BaseModel):
    path: str


class PathsIn(BaseModel):
    paths: list[str]


class JobIn(BaseModel):
    workbook: str
    documents: list[str] = []
    notes: str = ""


class TextIn(BaseModel):
    text: str


class AnswerIn(BaseModel):
    id: str
    value: str | None = None


def connection_problem() -> str | None:
    """Why the agent cannot reach Claude yet, in plain words (None when the settings look complete)."""
    if not os.environ.get("ANTHROPIC_FOUNDRY_ENDPOINT"):
        return "The Claude endpoint is not set up (ANTHROPIC_FOUNDRY_ENDPOINT)."
    return None


def create_app(token: str, desktop: Desktop | None = None) -> FastAPI:
    desktop = desktop or Desktop()
    app = FastAPI(title="Excel filler", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.desktop = desktop

    def check(request: Request) -> None:
        # Only this machine, only with the token handed to the window at launch.
        host = (request.headers.get("host") or "").split(":")[0]
        supplied = request.headers.get("x-token") or request.query_params.get("token") or ""
        if host not in ("127.0.0.1", "localhost", "testserver") or not secrets.compare_digest(supplied, token):
            raise HTTPException(403, "Forbidden")

    guarded = [Depends(check)]

    @app.get("/api/state", dependencies=guarded)
    def get_state():
        return {**desktop.listing(), "busy": desktop.busy, "connection_problem": connection_problem(),
                "pending": desktop.ui.pending_questions()}

    @app.post("/api/folder", dependencies=guarded)
    def open_folder(body: FolderIn):
        desktop.open(Path(body.path))
        return desktop.listing()

    @app.post("/api/workbook", dependencies=guarded)
    def open_workbook(body: FolderIn):
        """Open the workbook's folder, with the workbook preselected (the agent works in that folder)."""
        path = Path(body.path).expanduser()
        if path.suffix.lower() not in (".xlsx", ".xlsm"):
            raise HTTPException(400, f"{path.name} is not an Excel workbook (.xlsx or .xlsm). Older .xls files "
                                     "must first be saved as .xlsx in Excel.")
        if not path.is_file():
            raise HTTPException(400, f"File not found: {path}")
        desktop.open(path.resolve().parent, workbook=path.name)
        return desktop.listing()

    @app.post("/api/documents", dependencies=guarded)
    def add_documents(body: PathsIn):
        """Add documents chosen in a file dialog; they must be in the workbook's folder or below it."""
        if desktop.folder is None:
            raise HTTPException(400, "Open a workbook first.")
        added, outside = [], []
        for raw in body.paths:
            path = Path(raw).expanduser().resolve()
            if path.suffix.lower() not in DOCUMENT_TYPES or not path.is_file():
                outside.append(f"{path.name} (not a supported document)")
            elif desktop.folder not in path.parents:
                outside.append(f"{path.name} (outside {desktop.folder.name})")
            else:
                relative = path.relative_to(desktop.folder).as_posix()
                desktop.extra_documents.add(relative)
                added.append(relative)
        desktop.ui.emit({"type": "listing", **desktop.listing()})
        if outside:
            raise HTTPException(400, "Not added: " + ", ".join(outside) + ". Documents must be in the workbook's "
                                     "folder (or one of its subfolders); copy them there first.")
        return {**desktop.listing(), "added": added}

    @app.post("/api/job", dependencies=guarded)
    def start_job(body: JobIn):
        if desktop.folder is None:
            raise HTTPException(400, "Choose a folder first.")
        if problem := connection_problem():
            raise HTTPException(400, problem)
        desktop.run(lambda: agent.fill(body.workbook, body.documents, body.notes))
        return {"started": True}

    @app.post("/api/followup", dependencies=guarded)
    def follow_up(body: TextIn):
        if desktop.folder is None or not body.text.strip():
            raise HTTPException(400, "Nothing to send.")
        desktop.run(lambda: session.send(body.text.strip()))
        return {"started": True}

    @app.post("/api/answer", dependencies=guarded)
    def answer(body: AnswerIn):
        if not desktop.ui.answer(body.id, body.value or ""):
            raise HTTPException(404, "No such question.")
        return {"ok": True}

    @app.post("/api/stop", dependencies=guarded)
    def stop():
        session.stop()
        desktop.ui.cancel_questions()
        return {"ok": True}

    @app.websocket("/ws")
    async def events(ws: WebSocket):
        supplied = ws.query_params.get("token") or ""
        if not secrets.compare_digest(supplied, token):
            await ws.close(code=4403)
            return
        await ws.accept()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def listener(event: dict) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        history = desktop.ui.subscribe(listener)
        receiver = getter = None
        try:
            await ws.send_json({"type": "hello", "history": history, "busy": desktop.busy, **desktop.listing(),
                                "connection_problem": connection_problem()})
            receiver = asyncio.create_task(ws.receive_text())  # only to notice the window closing
            while True:
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({getter, receiver}, return_when=asyncio.FIRST_COMPLETED)
                if receiver in done:  # the window closed or reloaded; it reconnects and gets the history
                    break
                await ws.send_json(getter.result())
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass  # the connection dropped while sending
        finally:
            desktop.ui.unsubscribe(listener)
            for task in (receiver, getter):
                if task is not None:
                    # Collect each task's outcome (e.g. the disconnect) when it ends, so asyncio has
                    # nothing to report -- without awaiting here, which fails if we are being cancelled.
                    task.add_done_callback(lambda t: t.cancelled() or t.exception())
                    task.cancel()

    if (STATIC_DIR / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "index.html")

        @app.get("/favicon.svg")
        def favicon():
            return FileResponse(STATIC_DIR / "favicon.svg")
    else:
        @app.get("/")
        def not_built():
            return HTMLResponse("<h1>The UI is not built.</h1><p>Run <code>npm install && npm run build</code> "
                                "in <code>frontend/</code>, then restart.</p>", status_code=503)

    return app
