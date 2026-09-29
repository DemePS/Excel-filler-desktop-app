# Excel-filler-desktop-app

Fill an Excel workbook from PDF documents with Claude (Azure / Microsoft Foundry), reviewing
every change before it is saved.

You point it at a folder holding a workbook and the documents (invoices, statements, scans). It
opens the workbook first to see which fields are needed, reads only the document pages that hold
them, writes the values (you approve a cell-by-cell diff), checks them, and ends with the source
of every value. It never invents a value: missing or ambiguous ones are asked or left empty.

## How it is built

The agent engine is the [`coding_agent`](https://github.com/DemePS/weather/tree/claude/coding-agent-tools-8dvdd2)
package (agent loop, tools, safety rules, memory, context management), installed as a dependency.
This project only adds:

| | |
|---|---|
| `excel_filler/agent.py` | the tools Claude gets (read documents, read/write the workbook, ask you; no code execution, deletion or network), its instructions, and how a job is phrased |
| `excel_filler/cli.py` | the `excel-filler` terminal command |
| desktop window | *next step*: the same agent in a window (React UI, local FastAPI backend) |

## Try it (terminal)

```bash
uv sync
uv run excel-filler -d path/to/folder costs.xlsx invoice1.pdf invoice2.pdf -n "amounts excl. VAT, one row per line item"
```

Configuration (environment variables or a `.env` file in the folder you run from):

| Variable | Meaning |
|---|---|
| `ANTHROPIC_FOUNDRY_ENDPOINT` | `https://<resource>.services.ai.azure.com/anthropic` |
| `ANTHROPIC_FOUNDRY_API_KEY` | API key; leave unset to sign in with your Microsoft account (Azure AD) |
| `ANTHROPIC_FOUNDRY_DEPLOYMENT` | your Claude deployment name |

A copy of the previous version of every workbook it saves is kept in `~/.coding-agent/backups/`.

## Updating the agent engine

`pyproject.toml` pins `coding-agent` to a commit of DemePS/weather. To take a newer version,
change the ref after `@` and run `uv lock && uv sync`.

## Tests

```bash
uv run pytest -q
```

They run a whole filling job against a mocked Claude API through the real SDK and tools.

## Roadmap

1. ~~Agent engine as a package (`coding_agent`), imported here~~
2. Desktop window: pick a folder, a workbook and documents; watch progress; approve cell
   changes and answer questions in the window.
3. Sign-in: Microsoft account (Entra ID) or an API key kept in the OS keychain.
4. Windows installer built by CI.
