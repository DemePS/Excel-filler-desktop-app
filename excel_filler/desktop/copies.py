"""Working on a copy: the workbook is copied next to the original and the copy is what gets filled."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

WORKBOOK_TYPES = (".xlsx", ".xlsm")
COPY_SUFFIX = re.compile(r" \(copy(?: \d+)?\)$")  # "costs (copy)", "costs (copy 2)"


def copy_path(folder: Path, workbook: str) -> Path:
    """Where the copy of `workbook` goes: "costs (copy).xlsx", then "costs (copy 2).xlsx"... The copy of a copy
    is named from the original ("costs (copy 2)"), not "costs (copy) (copy)"."""
    source = Path(workbook)
    stem = COPY_SUFFIX.sub("", source.stem)
    candidate = folder / f"{stem} (copy){source.suffix}"
    number = 2
    while candidate.exists():
        candidate = folder / f"{stem} (copy {number}){source.suffix}"
        number += 1
    return candidate


def make_copy(folder: Path, workbook: str) -> str:
    """Copy a workbook of `folder` (never overwriting anything) and return the copy's name. Raises ValueError
    for a name that is not a workbook directly in the folder."""
    if Path(workbook).name != workbook or Path(workbook).suffix.lower() not in WORKBOOK_TYPES:
        raise ValueError(f"{workbook!r} is not a workbook (.xlsx or .xlsm) of the folder.")
    source = folder / workbook
    if not source.is_file():
        raise ValueError(f"File not found: {workbook}")
    target = copy_path(folder, workbook)
    shutil.copy2(source, target)  # the bytes as they are: a macro workbook keeps its macros
    return target.name
