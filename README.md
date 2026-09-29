# Excel-filler-desktop-app

Fill an Excel workbook from PDF documents with Claude (Azure / Microsoft Foundry), reviewing
every change before it is saved.

You open the workbook and pick the documents (invoices, statements, scans): those next to the
workbook, a documents folder of their own (**Choose a documents folder…**), or single files from
anywhere (**Add files…**). Folders outside the workbook's are read-only for the agent, which only
ever writes the workbook. It
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
| `excel_filler/desktop/` | the desktop window: a local FastAPI backend (127.0.0.1, per-launch token) running the agent in a worker thread, `WebUI` sending the agent's UI calls to the window over a WebSocket, and `app.py` opening a native window (pywebview) |
| `frontend/` | the window's React UI: choose a folder, pick the workbook and documents, watch the work, approve cell changes, answer Claude's questions, ask for corrections |

## Run the desktop app

```bash
uv sync --locked
uv run excel-filler-desktop            # native window (WebView2 on Windows)
uv run excel-filler-desktop --browser  # or in your browser
```

The window's UI comes already built (`excel_filler/desktop/static/`), so running the app needs
no Node.js. Only if you change the UI code in `frontend/`: `cd frontend && npm ci && npm run
build`, and commit the updated `excel_filler/desktop/static/` with your change.

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

## Versions

Every dependency is pinned to the exact version it was tested with: Python packages in
`pyproject.toml` (and all their own dependencies in `uv.lock`), the agent engine to a commit of
DemePS/weather, and the UI's packages in `frontend/package.json` (and `package-lock.json`). Install
exactly those with:

```bash
uv sync --locked          # fails instead of changing a version if uv.lock is out of date
cd frontend && npm ci     # only to change the UI
```

To upgrade something (for example the engine: the commit after `@` in `pyproject.toml`), change its
version, run `uv lock` (or `npm install` in `frontend/`), run the tests, and commit the lock file.

## Tests

```bash
uv run pytest -q
```

They run a whole filling job against a mocked Claude API through the real SDK and tools.

## Roadmap

1. ~~Agent engine as a package (`coding_agent`), imported here~~
2. ~~Desktop window: pick a folder, a workbook and documents; watch progress; approve cell
   changes and answer questions in the window.~~
3. Sign-in: Microsoft account (Entra ID) or an API key kept in the OS keychain.
4. Windows installer built by CI.
