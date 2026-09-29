"""Terminal front end: `excel-filler -d <folder> <workbook> <documents...>`.

The desktop window uses the same agent (excel_filler.agent); this command is handy to try it and
to script jobs.
"""

import argparse
from pathlib import Path

from coding_agent import session
from coding_agent.ui import TerminalUI, read_text

from . import agent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill an Excel workbook from PDF documents with Claude.")
    parser.add_argument("workbook", nargs="?", help="The .xlsx/.xlsm to fill, relative to the folder.")
    parser.add_argument("documents", nargs="*", help="PDFs or images to take the values from (default: all in the folder).")
    parser.add_argument("-d", "--dir", default=".", help="Folder holding the workbook and the documents (default: current).")
    parser.add_argument("-n", "--notes", default="", help="Extra instructions, e.g. 'amounts excl. VAT, one row per line item'.")
    parser.add_argument("-s", "--sheet", action="append", default=[], dest="sheets",
                        help="A sheet to fill (repeat for several); only those can be changed. Default: Claude finds them.")
    parser.add_argument("-r", "--resume", action="store_true", help="Continue the last conversation in this folder.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ui = TerminalUI()
    try:
        folder = agent.open_folder(args.dir, ui, resume=args.resume)
    except NotADirectoryError as e:
        raise SystemExit(str(e))
    workbooks = sorted(p.name for p in folder.glob("*.xls[xm]") if not p.name.startswith("~$"))
    documents = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg"))
    print(f"Folder: {folder}\nWorkbooks: {', '.join(workbooks) or '(none)'}\nDocuments: {', '.join(documents) or '(none)'}")
    workbook = args.workbook or (workbooks[0] if len(workbooks) == 1 else input("Workbook to fill: ").strip())
    if not (folder / workbook).is_file() and not Path(workbook).name.lower().endswith((".xlsx", ".xlsm")):
        raise SystemExit(f"Not a workbook: {workbook}")
    try:
        ok = agent.fill(workbook, args.documents or documents, args.notes, args.sheets)
        # Follow-up requests ("the dates are wrong in row 4") in the same conversation.
        while True:
            try:
                text = read_text("\n\033[1mFollow-up (or 'exit'):\033[0m ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in ("", "exit", "quit"):
                break
            ok = session.send(text)
    finally:
        session.close()
    raise SystemExit(0 if ok else 1)
