"""WebUI: the coding_agent UI interface, sent to the desktop window as events.

Everything the agent shows becomes a JSON event pushed to the window (over a WebSocket). Questions
(approvals, Claude's questions) are events too; the agent's thread then waits until the window
posts the answer back. Events are also kept in a history, so a reloaded window can catch up.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from pathlib import Path

from coding_agent.ui import UI

Listener = Callable[[dict], None]


class WebUI(UI):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.history: list[dict] = []
        self._listeners: list[Listener] = []
        self._pending: dict[str, dict] = {}  # question id -> {"event", "done": Event, "answer"}
        self._stopping = False  # after Stop, questions are answered negatively until the next job

    # --- plumbing
    def emit(self, event: dict) -> None:
        with self._lock:
            last = self.history[-1] if self.history else None
            if event["type"] == "text" and last and last["type"] == "text":
                # Keep the history compact: consecutive text chunks become one text event.
                self.history[-1] = {**last, "text": last["text"] + event["text"]}
            else:
                self.history.append(dict(event))
            listeners = list(self._listeners)
        for listener in listeners:
            listener(event)

    def subscribe(self, listener: Listener) -> list[dict]:
        """Register a listener; returns the history so far (sent before any new event)."""
        with self._lock:
            self._listeners.append(listener)
            return list(self.history)

    def unsubscribe(self, listener: Listener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def pending_questions(self) -> list[dict]:
        with self._lock:
            return [p["event"] for p in self._pending.values()]

    def answer(self, question_id: str, value: str) -> bool:
        """The window's answer to a question; False if there is no such pending question."""
        with self._lock:
            pending = self._pending.get(question_id)
        if pending is None:
            return False
        pending["answer"] = value
        pending["done"].set()
        return True

    def cancel_questions(self) -> None:
        """Answer every pending question negatively (the person pressed Stop or closed the window),
        and every question the stopping job still asks (e.g. "Why not?" after a refusal)."""
        with self._lock:
            self._stopping = True
            pending = list(self._pending.values())
        for p in pending:
            p["answer"] = None
            p["done"].set()

    def new_job(self) -> None:
        """A job starts: questions are asked again."""
        with self._lock:
            self._stopping = False

    def _ask(self, event: dict) -> str | None:
        with self._lock:
            if self._stopping:
                return None
        qid = uuid.uuid4().hex
        event = {**event, "id": qid}
        done = threading.Event()
        with self._lock:
            self._pending[qid] = {"event": event, "done": done, "answer": None}
        self.emit(event)
        done.wait()
        with self._lock:
            answer = self._pending.pop(qid)["answer"]
        self.emit({"type": "answered", "id": qid})
        return answer

    # --- the UI interface
    def status(self, text): self.emit({"type": "status", "text": text})
    def success(self, text): self.emit({"type": "success", "text": text})
    def failure(self, text): self.emit({"type": "failure", "text": text})
    def warning(self, text): self.emit({"type": "warning", "text": text})
    def message(self, text): self.emit({"type": "message", "text": text})

    def panel(self, title, lines=(), tone="change"):
        self.emit({"type": "panel", "title": title, "lines": list(lines), "tone": tone})

    def diff(self, action, name, path: Path, first_line, diff_lines):
        self.emit({"type": "diff", "action": action, "name": name, "path": str(path),
                   "first_line": first_line, "lines": diff_lines})

    def cell_changes(self, title, rows, more):
        self.emit({"type": "cells", "title": title, "more": more,
                   "rows": [{"cell": c, "old": o, "new": n, "format": f} for c, o, n, f in rows]})

    def confirm(self, question, choices=("yes", "no")):
        answer = self._ask({"type": "confirm", "question": question.strip(), "choices": list(choices)})
        return answer if answer in choices else ("no" if "no" in choices else choices[-1])

    def ask_text(self, prompt, multiline=False):
        answer = self._ask({"type": "ask", "prompt": prompt.strip(), "multiline": multiline})
        return (answer or "").strip()

    def assistant_start(self): self.emit({"type": "assistant_start"})
    def assistant_text(self, text): self.emit({"type": "text", "text": text})
    def thinking(self): self.emit({"type": "thinking"})
    def tool_start(self, name): self.emit({"type": "tool", "name": name})
    def tool_detail(self, text): self.emit({"type": "tool_detail", "text": text.strip()})
    def assistant_end(self): self.emit({"type": "assistant_end"})
