"""The local backend of the desktop window: a FastAPI app bound to 127.0.0.1.

The agent runs in a worker thread (one job at a time); its UI calls reach the window as WebSocket
events, and the window answers approvals and questions with POST /api/answer. Every request must
carry the per-launch token (a web page in a browser cannot guess it), so nothing else on the
machine can drive the agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import anthropic
from coding_agent import active_provider, make_anthropic_client, session, state
from coding_agent.config import BACKUP_HOME, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from coding_agent.errors import redact

from .. import agent, chart, help as help_guide
from . import copies, picker
from .joblog import JobLog, log as job_log
from .settings import Settings, valid_key
from .webui import WebUI

STATIC_DIR = Path(__file__).parent / "static"
DOCUMENT_TYPES = (".pdf", ".docx", ".pptx", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".txt", ".csv")


class Desktop:
    """The state of the window's single agent session."""

    def __init__(self) -> None:
        self.ui = WebUI()
        self.ui.subscribe(JobLog().on_event)  # what the agent does, in the terminal and the log file
        self.folder: Path | None = None
        self.workbook: str | None = None  # the workbook the person opened, preselected in the window
        # Documents added with the file dialog: relative paths inside the folder, absolute paths for
        # documents elsewhere (their folder is then readable by the agent, never writable).
        self.extra_documents: set[str] = set()
        # The folder the documents come from, when changed from the workbook's (None: the workbook's).
        self.documents_folder: Path | None = None
        self.busy = False
        self.auto = False  # auto mode: changes applied without asking (a backup is kept)
        self.lock = threading.Lock()

    def listing(self) -> dict:
        if self.folder is None:
            return {"folder": None, "workbooks": [], "documents": [], "workbook": None, "documents_folder": None}
        files = sorted((p for p in self.folder.iterdir() if p.is_file()), key=lambda p: p.name.lower())
        if self.documents_folder is None:
            documents = [p.name for p in files if p.suffix.lower() in DOCUMENT_TYPES]
        else:  # read again each time: documents added to that folder meanwhile show up
            documents = [self.document_name(p) for p in folder_documents(self.documents_folder)] if self.documents_folder.is_dir() else []
        documents += sorted(d for d in self.extra_documents if d not in documents and (self.folder / d).is_file())
        return {
            "folder": str(self.folder),
            "workbooks": [p.name for p in files if p.suffix.lower() in (".xlsx", ".xlsm") and not p.name.startswith("~$")],
            "documents": documents,
            "workbook": self.workbook,
            "documents_folder": str(self.documents_folder) if self.documents_folder else None,
        }

    def document_name(self, path: Path) -> str:
        """How the window and the job name a document: relative inside the workbook's folder, else absolute."""
        return path.relative_to(self.folder).as_posix() if self.folder in path.parents else path.as_posix()

    def open(self, folder: Path, workbook: str | None = None) -> None:
        if self.busy:
            raise HTTPException(409, "Wait for the current job to finish.")
        try:
            self.folder = agent.open_folder(folder, self.ui, auto=self.auto)
        except (NotADirectoryError, OSError) as e:
            raise HTTPException(400, str(e))
        self.workbook = workbook
        self.extra_documents = set()
        self.documents_folder = None
        self.ui.emit({"type": "listing", **self.listing()})

    def workbook_times(self) -> dict[str, int]:
        """Last change of each workbook in the folder (to see which ones a job saved)."""
        if self.folder is None:
            return {}
        return {p.name: p.stat().st_mtime_ns for p in self.folder.iterdir()
                if p.is_file() and p.suffix.lower() in (".xlsx", ".xlsm") and not p.name.startswith("~$")}

    def run(self, job, request: str = "") -> None:
        """Run a job (a function calling the agent) in a worker thread; `request` is what you asked,
        shown first in the window's feed."""
        with self.lock:
            if self.busy:
                raise HTTPException(409, "A job is already running.")
            self.busy = True
        self.ui.new_job()
        before = self.workbook_times()
        self.ui.emit({"type": "busy", "busy": True})
        if request:
            self.ui.emit({"type": "request", "text": request})

        def worker():
            try:
                job()
            except Exception as e:  # never let the worker die silently
                self.ui.message(f"[error] {type(e).__name__}: {e}")
            finally:
                # Each workbook the job saved: the window offers to open it.
                after = self.workbook_times()
                for name in sorted(n for n, t in after.items() if before.get(n) != t):
                    self.ui.emit({"type": "saved", "name": name, "path": str(self.folder / name),
                                  "backups": str(BACKUP_HOME)})
                with self.lock:
                    self.busy = False
                self.ui.emit({"type": "busy", "busy": False})
                self.ui.emit({"type": "listing", **self.listing()})  # the workbook may have changed

        threading.Thread(target=worker, name="agent-job", daemon=True).start()


class FolderIn(BaseModel):
    path: str


class PathsIn(BaseModel):
    paths: list[str]


class PickIn(BaseModel):
    kind: str  # workbook, documents or folder
    folder: str | None = None  # where the dialog opens


class JobIn(BaseModel):
    workbook: str
    documents: list[str] = []
    notes: str = ""
    sheets: list[str] = []  # the sheets to fill; none: ComptaIA finds them
    on_copy: bool = False  # fill a copy of the workbook, next to it: the original is not changed
    language: str = ""  # the window's language ("fr"): the agent writes its summary and questions in it


class TextIn(BaseModel):
    text: str
    language: str = ""


class AutoIn(BaseModel):
    on: bool


class AnswerIn(BaseModel):
    id: str
    value: str | None = None


class HelpIn(BaseModel):
    question: str
    history: list[dict] = []
    language: str = ""


class KeyIn(BaseModel):
    api_key: str


class ClientErrorIn(BaseModel):
    message: str
    stack: str | None = None


window_log = logging.getLogger("excel-filler.window")


def to_json(event: dict) -> str:
    """An event as JSON; a value JSON cannot encode (a date, a path) is sent as text rather than
    breaking the connection."""
    return json.dumps(event, default=str)


def job_request(workbook: str, documents: list[str], notes: str, sheets: list[str] | None = None) -> str:
    """Your request in plain words: "Fill costs.xlsx (sheet Costs) from invoice.pdf and scan.pdf"."""
    names = [Path(d).name for d in documents]
    listed = ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else "".join(names)
    if sheets:
        workbook += f" ({'sheet' if len(sheets) == 1 else 'sheets'} {', '.join(sheets)})"
    return f"Fill {workbook}" + (f" from {listed}" if listed else "") + (f"\n{notes.strip()}" if notes.strip() else "")


def folder_documents(folder: Path) -> list[Path]:
    """The PDFs and images of a folder (not its subfolders), by name."""
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in DOCUMENT_TYPES
                   and p.suffix.lower() not in (".txt", ".csv")), key=lambda p: p.name.lower())


def open_file(path: Path) -> None:
    """Open a file in its default application (Excel for a workbook)."""
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 -- a workbook of the job's folder, checked by the caller
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def connection_problem() -> str | None:
    """Why the agent cannot reach ComptaIA yet, in plain words (None when the settings look complete)."""
    if active_provider() is None:
        return "Add your API key in Settings to start."
    return None


def test_key(api_key: str) -> None:
    """One tiny call with this key, before it is saved. Raises HTTPException with a plain message."""
    name = "DeepSeek"
    client = make_anthropic_client(api_key, max_retries=0, timeout=15, base_url=DEEPSEEK_BASE_URL)
    try:
        client.messages.create(model=DEEPSEEK_MODEL, max_tokens=1, messages=[{"role": "user", "content": "ping"}])
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        raise HTTPException(401, f"{name} did not accept this key. Check that you copied all of it.")
    except anthropic.NotFoundError:
        raise HTTPException(400, "That model is not available to this key. Choose another model, or the default.")
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e).lower():
            raise HTTPException(402, f"The key is valid, but the account has no credit. Add credit on the {name} website "
                                     "(billing), then try again.")
        raise HTTPException(400, redact(f"{name} refused the test: {e.message}")[:300])
    except (anthropic.APIConnectionError, anthropic.APITimeoutError):
        raise HTTPException(502, f"Could not reach {name}. Check your internet connection, VPN or proxy, then try again.")
    except anthropic.APIStatusError as e:
        raise HTTPException(502, redact(f"{name} answered with an error (HTTP {e.status_code}). Try again in a moment.")[:300])


def create_app(token: str, desktop: Desktop | None = None, settings: Settings | None = None) -> FastAPI:
    desktop = desktop or Desktop()
    settings = settings or Settings()
    app = FastAPI(title="ComptaIA", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.desktop = desktop
    app.state.settings = settings

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # FastAPI's default answer echoes the request body, which can hold the API key.
        return JSONResponse({"detail": "The request was not valid."}, status_code=422)

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
                "pending": desktop.ui.pending_questions(), "auto": desktop.auto}

    @app.get("/api/settings", dependencies=guarded)
    def get_settings():
        return settings.info()

    @app.post("/api/help", dependencies=guarded)
    def help_answer(body: HelpIn):
        """"A problem?": the support agent answers from the guide and the end of the log (no tools, separate from the job)."""
        question = body.question.strip()
        if not question:
            raise HTTPException(400, "Type a question.")
        if len(question) > help_guide.MAX_QUESTION:
            raise HTTPException(400, f"Keep the question under {help_guide.MAX_QUESTION} characters.")
        if active_provider() is None:
            raise HTTPException(409, connection_problem() or "Add your API key in Settings first.")
        from coding_agent.config import get_model
        try:
            answer = help_guide.ask(session._get_client(), get_model(), question, body.history, body.language,
                                    help_guide.log_tail(redact=redact))
        except Exception as e:
            from coding_agent.errors import describe
            raise HTTPException(502, redact(describe(e) or f"{type(e).__name__}: {e}")[:300])
        job_log.info("Support question answered (%d characters)", len(answer))
        return {"answer": answer or "…"}

    @app.post("/api/settings", dependencies=guarded)
    def save_settings(body: KeyIn):
        """Test the key with one tiny call, then save it (Credential Manager) and use it from now on."""
        key = body.api_key.strip()
        if not valid_key(key):
            raise HTTPException(400, "That does not look like an API key (it is one long line of letters and digits, "
                                     "starting with sk-).")
        if desktop.busy:
            raise HTTPException(409, "Wait for the current job to finish.")
        test_key(key)  # outside the lock: it can take 15 s
        with settings.lock:
            if desktop.busy:
                raise HTTPException(409, "Wait for the current job to finish.")
            settings.save(key)
        job_log.info("API key saved (ends with %s)", key[-4:])
        return settings.info()

    @app.delete("/api/settings/key", dependencies=guarded)
    def remove_key():
        with settings.lock:
            if desktop.busy:
                raise HTTPException(409, "Wait for the current job to finish.")
            settings.remove()
        job_log.info("API key removed")
        return settings.info()

    @app.post("/api/auto", dependencies=guarded)
    def set_auto(body: AutoIn):
        """Auto mode on or off: changes applied without asking (a backup of the workbook is still kept;
        a workbook whose features saving would damage still asks), and ComptaIA's questions not asked."""
        if desktop.busy:
            raise HTTPException(409, "Wait for the current job to finish.")
        desktop.auto = body.on
        if desktop.folder is not None:
            agent.set_auto(body.on)
        job_log.info("Auto mode %s", "on: changes are applied without asking" if body.on else "off")
        desktop.ui.emit({"type": "auto", "on": body.on})
        return {"auto": desktop.auto}

    @app.get("/api/check", dependencies=guarded)
    def check():
        """Can the app reach ComptaIA? A 1-token call; the window shows the answer at startup."""
        if problem := connection_problem():
            return {"ok": False, "message": problem}
        started = time.monotonic()
        ok, message = session.check_connection()
        took = f"{time.monotonic() - started:.1f} s"
        (job_log.info if ok else job_log.error)("Connection check (%s): %s", took, message if not ok else "OK, " + message)
        return {"ok": ok, "message": message}

    @app.get("/api/pick/available", dependencies=guarded)
    def pick_available():
        """Whether the backend can show a file dialog itself (browser mode on Linux: zenity)."""
        return {"available": picker.available()}

    @app.post("/api/pick", dependencies=guarded)
    def pick_paths(body: PickIn):
        """Show the system's file dialog on this machine and return the paths chosen ([] if cancelled)."""
        if body.kind not in picker.TITLES:
            raise HTTPException(400, f"Unknown dialog: {body.kind}")
        if not picker.available():
            raise HTTPException(501, "No file dialog is available on this system.")
        try:
            return {"paths": picker.pick(body.kind, body.folder)}
        except RuntimeError as e:
            raise HTTPException(502, str(e))

    @app.get("/api/chart-of-accounts", dependencies=guarded)
    def chart_of_accounts():
        """The file the agent looks accounts up in (None until one is installed)."""
        folder = agent.knowledge_target()
        file = chart.current(folder)
        return {"file": file.name if file else None, "folder": str(folder),
                "modified": file.stat().st_mtime if file else None}

    @app.post("/api/chart-of-accounts", dependencies=guarded)
    def update_chart_of_accounts(body: FolderIn):
        """Replace the chart of accounts of the knowledge folder by the chosen file (indexed at once)."""
        if desktop.busy:
            raise HTTPException(409, "A job is running: update the chart of accounts when it is finished.")
        folder = agent.knowledge_target()
        try:
            installed = chart.install(body.path, folder)
        except chart.ChartError as e:
            raise HTTPException(400, str(e))
        if state.workspace is not None:
            session.add_read_folder(folder)  # a session already open: the agent can read it from the next instruction
        job_log.info("Chart of accounts updated: %s", installed.name)
        return chart_of_accounts()

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
        """Add documents chosen in a file dialog, from any folder. A document outside the workbook's
        folder makes its folder readable by the agent (read-only: the agent only writes the workbook)."""
        if desktop.folder is None:
            raise HTTPException(400, "Open a workbook first.")
        if desktop.busy:
            raise HTTPException(409, "Wait for the current job to finish.")
        added, refused = [], []
        for raw in body.paths:
            path = Path(raw).expanduser().resolve()
            if path.suffix.lower() not in DOCUMENT_TYPES or not path.is_file():
                refused.append(path.name)
                continue
            if desktop.folder in path.parents:
                name = path.relative_to(desktop.folder).as_posix()
            else:
                session.add_read_folder(path.parent)
                name = path.as_posix()
            desktop.extra_documents.add(name)
            added.append(name)
        desktop.ui.emit({"type": "listing", **desktop.listing()})
        if refused:
            raise HTTPException(400, "Not added (not a PDF, image or text document): " + ", ".join(refused))
        return {**desktop.listing(), "added": added}

    def document_folder(raw: str) -> tuple[Path, list[str]]:
        """A folder chosen for documents, made readable by the agent (read-only) when outside the
        workbook's, and its documents as the job names them."""
        if desktop.folder is None:
            raise HTTPException(400, "Open a workbook first.")
        if desktop.busy:
            raise HTTPException(409, "Wait for the current job to finish.")
        folder = Path(raw).expanduser().resolve()
        if folder.is_file():  # a document of the folder was picked (the file dialog shows the files)
            folder = folder.parent
        if not folder.is_dir():
            raise HTTPException(400, f"Not a folder: {folder}")
        paths = folder_documents(folder)
        if not paths:
            raise HTTPException(400, f"No PDF, Word, PowerPoint or image in {folder} (documents in its subfolders are not included).")
        inside = folder == desktop.folder or desktop.folder in folder.parents
        if not inside:
            session.add_read_folder(folder)
        job_log.info("Documents folder %s: %d document(s)%s", folder, len(paths), "" if inside else " (read-only)")
        return folder, [desktop.document_name(p) for p in paths]

    @app.post("/api/document-folder", dependencies=guarded)
    def add_document_folder(body: FolderIn):
        """Add every document of a folder (PDFs and images, not its subfolders). A folder outside the
        workbook's becomes readable by the agent, read-only."""
        _, added = document_folder(body.path)
        desktop.extra_documents.update(added)
        desktop.ui.emit({"type": "listing", **desktop.listing()})
        return {**desktop.listing(), "added": added}

    @app.post("/api/document-folder/change", dependencies=guarded)
    def change_document_folder(body: FolderIn):
        """Take the documents from this folder instead: only its documents are listed (not the
        workbook folder's, nor those added before)."""
        folder, added = document_folder(body.path)
        desktop.documents_folder = None if folder == desktop.folder else folder
        desktop.extra_documents = set()
        desktop.ui.emit({"type": "listing", **desktop.listing()})
        return {**desktop.listing(), "added": added}

    @app.post("/api/document-folder/reset", dependencies=guarded)
    def reset_document_folder():
        """Back to the documents next to the workbook."""
        if desktop.busy:
            raise HTTPException(409, "Wait for the current job to finish.")
        desktop.documents_folder = None
        desktop.extra_documents = set()
        desktop.ui.emit({"type": "listing", **desktop.listing()})
        return desktop.listing()

    @app.get("/api/sheets", dependencies=guarded)
    def sheets(workbook: str):
        """The sheets of a workbook of the folder, with their sizes (for choosing the ones to fill)."""
        if desktop.folder is None or workbook not in desktop.listing()["workbooks"]:
            raise HTTPException(400, "Only a workbook of the open folder.")
        import openpyxl
        try:
            wb = openpyxl.load_workbook(desktop.folder / workbook, read_only=True)
        except Exception as e:  # locked, damaged...
            raise HTTPException(400, f"Could not read {workbook}: {e}")
        try:
            return {"sheets": [{"name": ws.title, "rows": ws.max_row or 0, "cols": ws.max_column or 0}
                               for ws in wb.worksheets]}
        finally:
            wb.close()

    @app.post("/api/open", dependencies=guarded)
    def open_workbook_in_excel(body: TextIn):
        """Open a workbook of the folder in Excel (only a workbook listed in the folder)."""
        if desktop.folder is None or body.text not in desktop.listing()["workbooks"]:
            raise HTTPException(400, "Only a workbook of the open folder can be opened.")
        try:
            open_file(desktop.folder / body.text)
        except OSError as e:
            raise HTTPException(500, f"Could not open {body.text}: {e}")
        job_log.info("Opened %s in its application", body.text)
        return {"ok": True}

    @app.post("/api/job", dependencies=guarded)
    def start_job(body: JobIn):
        if desktop.folder is None:
            raise HTTPException(400, "Choose a folder first.")
        job_log.info("Fill %s from %d document(s)%s", body.workbook, len(body.documents),
                     " with instructions" if body.notes.strip() else "")
        with settings.lock:  # not while a key is being saved
            if problem := connection_problem():
                raise HTTPException(400, problem)
            if desktop.busy:
                raise HTTPException(409, "Wait for the current job to finish.")
            workbook = body.workbook
            if body.on_copy:  # the job fills a copy; the original is never opened for writing
                try:
                    workbook = copies.make_copy(desktop.folder, body.workbook)
                except (ValueError, OSError) as e:
                    raise HTTPException(400, str(e))
                job_log.info("Working on a copy: %s", workbook)
                desktop.workbook = workbook
                desktop.ui.emit({"type": "listing", **desktop.listing()})
            desktop.run(lambda: agent.fill(workbook, body.documents, body.notes, body.sheets, body.language),
                        job_request(workbook, body.documents, body.notes, body.sheets))
        return {"started": True, "workbook": workbook}

    @app.post("/api/followup", dependencies=guarded)
    def follow_up(body: TextIn):
        if desktop.folder is None or not body.text.strip():
            raise HTTPException(400, "Nothing to send.")
        if problem := connection_problem():
            raise HTTPException(400, problem)
        job_log.info("Follow-up request")
        with settings.lock:
            hint = agent.language_hint(body.language)
            desktop.run(lambda: session.send(body.text.strip() + (f"\n\n({hint})" if hint else "")), body.text.strip())
        return {"started": True}

    @app.post("/api/answer", dependencies=guarded)
    def answer(body: AnswerIn):
        if not desktop.ui.answer(body.id, body.value or ""):
            raise HTTPException(404, "No such question.")
        job_log.info("You answered: %s", {"yes": "approved", "no": "rejected"}.get(body.value or "", "(text reply)" if body.value else "(no answer)"))
        return {"ok": True}

    @app.post("/api/stop", dependencies=guarded)
    def stop():
        job_log.info("You pressed Stop")
        session.stop()
        desktop.ui.cancel_questions()
        return {"ok": True}

    @app.post("/api/client-error", dependencies=guarded)
    def client_error(body: ClientErrorIn):
        # An error in the window's code: logged, since the window itself may not be able to show it.
        window_log.error("Window error: %s%s", redact(body.message[:2000]), f"\n{redact(body.stack[:4000])}" if body.stack else "")
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
            await ws.send_text(to_json({"type": "hello", "history": history, "busy": desktop.busy, "auto": desktop.auto,
                                        **desktop.listing(), "connection_problem": connection_problem()}))
            receiver = asyncio.create_task(ws.receive_text())  # only to notice the window closing
            while True:
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({getter, receiver}, return_when=asyncio.FIRST_COMPLETED)
                if receiver in done:  # the window closed or reloaded; it reconnects and gets the history
                    break
                await ws.send_text(to_json(getter.result()))
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
