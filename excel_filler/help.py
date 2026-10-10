"""The Help button: questions about ComptaIA and about what it did, answered by the agent of the job.

With a folder open, the question goes to the same session as the filling (same agent, same conversation,
so it can explain what it read and why it wrote a value); no workbook can be changed during that turn.
Before any folder is open there is no job to ask about: a plain call with the guide answers.
"""

from __future__ import annotations

MAX_QUESTION = 1000   # characters of one question
MAX_TURNS = 8         # earlier messages kept, so a long chat does not grow without end
MAX_ANSWER_TOKENS = 700

INTRO = """\
You are the help of ComptaIA, a desktop application that fills a person's Excel templates from accounting
documents. Answer the person's questions about USING the application, briefly (a few sentences or a short
list), in the language of their question. If the question is about something else (general accounting
questions, writing, code, other software), say that you only help with using ComptaIA and give the
nearest thing the application can do. Never invent a feature: if the guide below does not say it, say
that ComptaIA does not do it or that you do not know. You cannot see the person's files or workbook.
"""

GUIDE = """\
How ComptaIA works
- "Open workbook…" picks the Excel template (.xlsx or .xlsm; an old .xls must first be saved as .xlsx).
  The documents are the files in the workbook's folder; "Change folder…", "Add folder…" and "Add files…"
  take documents from elsewhere. Documents are only ever read.
- Documents it reads: PDF (text, and scans), images (PNG, JPG, WebP, GIF), Word .docx (text and tables),
  PowerPoint .pptx (text and notes), text and CSV files. Not read: .doc, .ppt, .xls, .odt.
- Sheets: tick the sheets to fill; only those can be changed. None ticked: ComptaIA chooses.
- Instructions (optional): rules for this job, for example "amounts excluding VAT, one row per invoice line".
- "Work on a copy" (ticked by default) copies the workbook next to the original and fills the copy.
- "Fill workbook" starts the job. ComptaIA reads the workbook first, then the documents, then proposes the
  cell changes. You approve or reject each proposal, or "Always" for the rest. Auto mode applies changes
  without asking and asks no questions; missing values stay empty and are listed. A backup of the workbook
  is kept before every change.
- Formulas are never overwritten or cleared. Only the chosen workbook can be changed, and no other file
  is created or deleted.
- At the end ComptaIA says where each value came from and what it could not fill. Use the box at the bottom
  to ask for a correction (for example "use the invoice date, not the due date").
- Account numbers: ComptaIA looks them up in the chart of accounts (plan comptable) of its knowledge
  folder, and in the sheet of the workbook that lists the accounts, instead of writing them from memory.
  "Update chart of accounts" replaces that chart with a PDF or text file you choose.
- Scanned documents are read too (OCR or by looking at the page). Check names, dates and amounts taken
  from a scan: they can be misread.
- Settings: paste your DeepSeek API key; "Get my API key" opens DeepSeek's page where you create one.
  The key is saved on this PC (Windows Credential Manager) and sent only to DeepSeek, which bills you for
  use. The language button switches French and English.
- Privacy: the text and images of the documents that are read are sent to DeepSeek, to be read by the
  model. ComptaIA has no server of its own.
- ComptaIA does not replace an accountant, does not file returns and does not make payments.
"""


def instruction(question: str, language: str = "") -> str:
    """What the job's agent receives for a help question: the question, the guide, and the rule that it only answers."""
    name = {"fr": "French", "en": "English"}.get(language)
    return (f"Help question from the person (not a request to change anything: do not edit any workbook). Answer it "
            f"briefly, from what you did in this job and from the guide below.{f' Answer in {name}.' if name else ''}\n\n"
            f"Question: {question[:MAX_QUESTION]}\n\nGuide of the application:\n{GUIDE}")


def clean_history(history: list[dict]) -> list[dict]:
    """The earlier turns that are kept: roles user / assistant alternating, text only, bounded."""
    kept = []
    for turn in history[-MAX_TURNS:]:
        role, text = turn.get("role"), str(turn.get("text", ""))[:2000]
        if role in ("user", "assistant") and text.strip():
            kept.append({"role": role, "content": text})
    while kept and kept[0]["role"] != "user":
        kept.pop(0)
    merged: list[dict] = []
    for turn in kept:  # the API wants alternating roles
        if merged and merged[-1]["role"] == turn["role"]:
            merged[-1]["content"] += "\n" + turn["content"]
        else:
            merged.append(turn)
    return merged


def ask(client, model: str, question: str, history: list[dict], language: str = "") -> str:
    """One answer of the model to a question about the application."""
    system = INTRO + GUIDE + (f"\nAnswer in {'French' if language == 'fr' else 'English'}.\n" if language in ("fr", "en") else "")
    messages = clean_history(history) + [{"role": "user", "content": question[:MAX_QUESTION]}]
    if len(messages) > 1 and messages[-2]["role"] == "user":  # two user turns in a row: merge
        messages[-2]["content"] += "\n" + messages.pop()["content"]
    reply = client.messages.create(model=model, max_tokens=MAX_ANSWER_TOKENS, system=system, messages=messages)
    return "".join(b.text for b in reply.content if getattr(b, "type", "") == "text").strip()
