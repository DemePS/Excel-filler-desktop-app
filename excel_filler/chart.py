"""The chart of accounts (plan comptable) of the knowledge folder, and its update.

The agent looks account numbers up in the reference texts of the knowledge folder (search_library). The chart of
accounts is the file `plan-comptable.<ext>` of that folder: updating it replaces that one file, never another, and
the file is indexed at once so the next job finds it. A file that cannot be read leaves the previous one in place.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from coding_agent import index

NAME = "plan-comptable"
TYPES = (".pdf", *index.TEXT_SUFFIXES)  # what search_library reads: a CSV or a workbook of accounts would never be found
# Not under ~/.coding-agent: the engine never reads there (credentials, its own settings), so the agent could
# search the chart (the index) but not open its pages.
DEFAULT_FOLDER = Path.home() / "ComptaIA" / "base-de-connaissance"
LEGACY_FOLDER = Path.home() / ".coding-agent" / "excel-filler-knowledge"  # where an earlier version put it


class ChartError(Exception):
    """A reason the chart could not be updated, in words for the person."""


def migrate_legacy(legacy: Path | None = None, target: Path | None = None) -> bool:
    """Move the knowledge folder of an earlier version to its new place (once). True when it was moved."""
    legacy, target = legacy or LEGACY_FOLDER, target or DEFAULT_FOLDER
    if not legacy.is_dir() or target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy), str(target))
    return True


def current(folder: Path) -> Path | None:
    for extension in TYPES:
        candidate = folder / f"{NAME}{extension}"
        if candidate.is_file():
            return candidate
    return None


def install(source: str | Path, folder: Path) -> Path:
    """Make `source` the chart of accounts of `folder` (created when missing). Returns the installed file."""
    source = Path(source).expanduser()
    if not source.is_file():
        raise ChartError(f"File not found: {source}")
    if source.suffix.lower() not in TYPES:
        raise ChartError(f"The chart of accounts must be a PDF or a text file (.txt, .md) (not {source.suffix or 'a file without extension'}).")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{NAME}{source.suffix.lower()}"
    if source.resolve() == target.resolve():
        raise ChartError("This file is already the chart of accounts.")
    previous = [p for p in (folder / f"{NAME}{e}" for e in TYPES) if p.is_file()]
    keep = Path(tempfile.mkdtemp(prefix="chart-previous-"))
    try:
        for p in previous:
            shutil.copy2(p, keep / p.name)
            p.unlink()
        shutil.copy2(source, target)
        errors: dict = {}
        index.refresh(folder, errors=errors)
        if str(target) in {str(k) for k in errors} or not index.connect(folder).execute(
                "SELECT 1 FROM docs WHERE path = ? AND pages > 0", (str(target),)).fetchone():
            why = next((str(v) for k, v in errors.items() if str(k) == str(target)), "no text could be read from it (a scan?)")
            raise ChartError(f"{source.name} cannot be used as chart of accounts: {why}")
    except Exception:
        target.unlink(missing_ok=True)
        for saved in keep.iterdir():
            shutil.copy2(saved, folder / saved.name)
        index.refresh(folder)
        raise
    finally:
        shutil.rmtree(keep, ignore_errors=True)
    return target
