"""Reading Word files: read_word.

CodeAgent reads PDF, Excel, images and text, not Word. A .docx is a zip of XML files, so its text is read with the
standard library (no extra dependency): the paragraphs in order, and the rows of the tables as "cell | cell".
Only the text is read: a picture inside the document is not (send it as an image or a PDF).
"""

import xml.etree.ElementTree as ET
import zipfile

from coding_agent import register_tool
from coding_agent.common import ToolError, resolve_readable, truncate

WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_registered = False


def _words(element, tag: str) -> str:
    return "".join(t.text or "" for t in element.iter(f"{{{WORD}}}{tag}"))


def read_word(path: str) -> str:
    """The text of a Word (.docx) file."""
    p = resolve_readable(path)
    if not p.is_file():
        raise ToolError(f"File not found: {path}")
    if p.suffix.lower() == ".doc":
        raise ToolError(f"{path} is an old .doc file: save it as .docx (or PDF) first.")
    if p.suffix.lower() != ".docx":
        raise ToolError(f"{path} is not a .docx file.")
    try:
        with zipfile.ZipFile(p) as z:
            body = ET.fromstring(z.read("word/document.xml")).find(f"{{{WORD}}}body")
    except zipfile.BadZipFile:
        raise ToolError(f"{path} is not a valid .docx file.")
    except (KeyError, ET.ParseError):
        raise ToolError(f"{path} has no readable document text.")
    lines = []
    for block in body:
        if block.tag == f"{{{WORD}}}p":
            lines.append(_words(block, "t").strip())
        elif block.tag == f"{{{WORD}}}tbl":
            for row in block.iter(f"{{{WORD}}}tr"):
                lines.append(" | ".join(_words(cell, "t").strip() for cell in row.iter(f"{{{WORD}}}tc")))
    return truncate("\n".join(line for line in lines if line) or "(no text in this document)")


SCHEMA = {
    "name": "read_word",
    "description": "Read the text of a Word (.docx) document: its paragraphs and the rows of its tables. Not for PDF, "
                   "Excel or images (they have their own tools). Pictures inside the document are not read.",
    "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "Path of the .docx file."}},
                     "required": ["path"]},
}


def register_office_tools() -> None:
    """Make read_word available to the agent (once)."""
    global _registered
    if not _registered:
        register_tool(SCHEMA, read_word)
        _registered = True
