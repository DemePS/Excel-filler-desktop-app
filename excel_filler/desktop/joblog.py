"""A readable log of what the agent does during a job, built from the same events the window gets.

One line per step (job start/end, each tool call with its arguments and outcome, proposed changes, approvals, questions,
Claude's messages, errors), in the terminal and in the log file. Document contents are not logged,
only file names, cell counts and Claude's own sentences.
"""

from __future__ import annotations

import logging
import re
import time

log = logging.getLogger("excel-filler.job")

TOOL_WORDS = {
    "read_excel": "reads the workbook",
    "edit_excel": "prepares changes to",
    "read_pdf": "reads",
    "view_image": "looks at",
    "read_file": "reads",
    "list_directory": "lists",
    "ask_human": "asks you a question",
}


def one_line(text: str, limit: int = 400) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + " …"


class JobLog:
    """Subscribe with WebUI.subscribe(job_log.on_event)."""

    def __init__(self) -> None:
        self.started = 0.0
        self.tool: str | None = None
        self.text: list[str] = []

    def on_event(self, event: dict) -> None:
        try:
            self._handle(event)
        except Exception:  # logging must never break a job
            log.exception("Could not log an event")

    def _flush_text(self) -> None:
        if "".join(self.text).strip():
            log.info("Claude: %s", one_line("".join(self.text)))
        self.text = []

    def _flush_tool(self, detail: str = "") -> None:
        if self.tool:
            words = TOOL_WORDS.get(self.tool, f"uses {self.tool}")
            log.info("Claude %s%s", words, f" {detail}" if detail else "")
            self.tool = None

    def _handle(self, event: dict) -> None:
        kind = event["type"]
        if kind == "busy":
            if event["busy"]:
                self.started = time.monotonic()
                log.info("Job started")
            else:
                self._flush_tool()
                log.info("Job finished in %.0f s", time.monotonic() - self.started)
        elif kind == "tool":
            self._flush_text()  # what Claude wrote comes before the tool it then uses
            self._flush_tool()
            self.tool = event["name"]
        elif kind == "tool_detail":
            file = re.search(r"path='([^']+)'", event["text"])
            pages = re.search(r"pages='([^']+)'", event["text"])
            detail = (file.group(1) if file else "") + (f" (page {pages.group(1)})" if pages else "")
            self._flush_tool(detail)
        elif kind == "tool_result":
            self._flush_tool()
            call = f"Tool {event['name']}({event.get('arguments') or ''})"
            if event.get("ok"):
                log.info("%s -> OK (%s)", call, event.get("summary") or "")
            else:
                log.warning("%s -> ERROR: %s", call, event.get("summary") or "")
        elif kind == "text":
            self.text.append(event["text"])
        elif kind == "assistant_end":
            self._flush_text()
            self._flush_tool()
        elif kind == "cells":
            log.info("%s -- waiting for your approval", event["title"])
        elif kind == "confirm":
            log.info("Question: %s", event["question"])
        elif kind == "panel" and event.get("tone") == "question":
            log.info("Claude asks: %s", one_line(event["title"]))
        elif kind == "success":
            log.info("Done: %s", event["text"])
        elif kind == "failure":
            log.warning("Not done: %s", event["text"])
        elif kind == "warning":
            log.warning("%s", event["text"])
        elif kind == "error":
            log.error("%s", event["text"])
        elif kind == "message":
            log.info("%s", event["text"])
        elif kind == "status" and not event["text"].startswith(("[context]", "[memory]")):
            log.info("%s", event["text"])
