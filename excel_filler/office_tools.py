"""Reading Word and PowerPoint files: read_word, read_powerpoint.

CodeAgent reads PDF, Excel, images and text, not Office documents. A .docx or .pptx is a zip of XML files, so its
text is read with the standard library (no extra dependency): a Word document's paragraphs in order and the rows of
its tables as "cell | cell"; a presentation slide by slide, with its speaker notes. Only the text is read: a picture
inside the document is not (send it as an image or a PDF).
"""

import re
import xml.etree.ElementTree as ET
import zipfile

from coding_agent import register_tool
from coding_agent.common import ToolError, resolve_readable, truncate

WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
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


def _slide_text(root) -> str:
    paragraphs = ("".join(t.text or "" for t in p.iter(f"{{{DRAWING}}}t")).strip() for p in root.iter(f"{{{DRAWING}}}p"))
    return "\n".join(line for line in paragraphs if line)


def read_powerpoint(path: str) -> str:
    """The text of a PowerPoint (.pptx) file, slide by slide, with the speaker notes."""
    p = resolve_readable(path)
    if not p.is_file():
        raise ToolError(f"File not found: {path}")
    if p.suffix.lower() == ".ppt":
        raise ToolError(f"{path} is an old .ppt file: save it as .pptx (or PDF) first.")
    if p.suffix.lower() != ".pptx":
        raise ToolError(f"{path} is not a .pptx file.")
    try:
        z = zipfile.ZipFile(p)
    except zipfile.BadZipFile:
        raise ToolError(f"{path} is not a valid .pptx file.")
    with z:
        number = lambda n: int(re.search(r"(\d+)\.xml$", n).group(1))  # noqa: E731
        slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=number)
        notes = {number(n): n for n in z.namelist() if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)}
        parts = []
        for name in slides:
            try:
                text = _slide_text(ET.fromstring(z.read(name)))
                note = _slide_text(ET.fromstring(z.read(notes[number(name)]))) if number(name) in notes else ""
            except ET.ParseError:
                raise ToolError(f"{path}: slide {number(name)} cannot be read.")
            parts.append(f"--- slide {number(name)} ---\n{text}" + (f"\n(notes) {note}" if note else ""))
    return truncate("\n\n".join(parts) or "(no slides in this presentation)")


SCHEMA = {
    "name": "read_word",
    "description": "Read the text of a Word (.docx) document: its paragraphs and the rows of its tables. Not for PDF, "
                   "Excel or images (they have their own tools). Pictures inside the document are not read.",
    "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "Path of the .docx file."}},
                     "required": ["path"]},
}


POWERPOINT_SCHEMA = {
    "name": "read_powerpoint",
    "description": "Read the text of a PowerPoint (.pptx) presentation, slide by slide, with its speaker notes. Not for PDF, "
                   "Excel or images (they have their own tools). Pictures inside the slides are not read.",
    "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "Path of the .pptx file."}},
                     "required": ["path"]},
}


def register_office_tools() -> None:
    """Make read_word and read_powerpoint available to the agent (once)."""
    global _registered
    if not _registered:
        register_tool(SCHEMA, read_word)
        register_tool(POWERPOINT_SCHEMA, read_powerpoint)
        _registered = True
