# ComptaIA

Fill an Excel workbook from PDF documents with Claude, reviewing every change before it is saved. It
runs on your own Anthropic API key (entered in the window) or on Azure / Microsoft Foundry.

You open the workbook and pick the documents (invoices, statements, scans): those next to the
workbook, the documents of another folder instead (**Change folder…**; **Use the workbook's folder**
goes back), more folders (**Add folder…**), or single files from anywhere (**Add files…**). Folders outside the workbook's are read-only for the agent, which only
ever writes the workbook. It
opens the workbook first to see which fields are needed, reads only the document pages that hold
them, writes the values (you approve a cell-by-cell diff), checks them, and ends with the source
of every value. It never invents a value: missing or ambiguous ones are asked or left empty.

## How it is built

The agent engine is the [`coding_agent`](https://github.com/DemePS/CodeAgent)
package (agent loop, tools, safety rules, memory, context management), installed as a dependency.
This project only adds:

| | |
|---|---|
| `excel_filler/agent.py` | the tools Claude gets (read documents, read/write the workbook, ask you; no code execution, deletion or network), its instructions, and how a job is phrased |
| `excel_filler/cli.py` | the `comptaia` terminal command |
| `excel_filler/desktop/` | the desktop window: a local FastAPI backend (127.0.0.1, per-launch token) running the agent in a worker thread, `WebUI` sending the agent's UI calls to the window over a WebSocket, and `app.py` opening a native window (pywebview) |
| `excel_filler/desktop/settings.py` | the Anthropic API key (Windows Credential Manager through `keyring`, session-only if there is none) and the chosen model; the key is tested with one call before it is saved |
| `frontend/` | the window's React UI: choose a folder, pick the workbook and documents, watch the work, approve cell changes, answer Claude's questions, ask for corrections, and the Settings / first-run key screen |
| `packaging/` | the PyInstaller recipe for the Windows app (see *Build the Windows app*) |

## Names and trademarks

ComptaIA is an independent project. It is **not affiliated with, endorsed by or sponsored by** Anthropic,
Microsoft or any model provider. Names such as Claude, Anthropic, DeepSeek, Microsoft and Excel are trademarks
of their owners and are used here only to say what the application works with (for example "works with an
Anthropic API key", "reads and writes .xlsx workbooks"). The former command names `excel-filler` and
`excel-filler-desktop` still work and point to the same programs.


## Run the desktop app

```bash
uv sync --locked
uv run comptaia-desktop            # native window (WebView2 on Windows)
uv run comptaia-desktop --browser  # or in your browser
```

The window's UI comes already built (`excel_filler/desktop/static/`), so running the app needs
no Node.js. Only if you change the UI code in `frontend/`: `cd frontend && npm ci && npm run
build`, and commit the updated `excel_filler/desktop/static/` with your change.

## Windows and Linux

The same code runs on both; what differs is the window and the file dialogs.

| | Window | File dialogs |
|---|---|---|
| **Windows** | native window (WebView2); the browser if it cannot open | the window's own dialogs; in the browser, tkinter's (Python's Tk) |
| **Linux** | a native window if GTK (`gi`) or Qt (`qtpy`) is installed, e.g. `uv pip install "pywebview[qt]"`; otherwise the browser, with one log line | in the browser, `zenity` if installed, else tkinter's; if neither, the path is typed |

Opening a workbook uses the system's default application on each system (Excel, `xdg-open`). The API
key goes to the Windows Credential Manager, or to the Linux Secret Service when there is one; without a
keyring it is kept for the session only and the Settings dialog says so. The Windows build recipe
(PyInstaller) is Windows-only; running from the sources works on both with `uv sync --locked`.

## Claude access

Two ways, in this order of precedence:

1. **Your Anthropic API key** (get one at [console.anthropic.com](https://console.anthropic.com)). On first launch the
   window asks for it; **Settings** (top right) changes it, picks the model, or removes the key. The key is tested with one
   tiny call, then kept in the Windows Credential Manager: never in a file, never in the log, and sent only to Anthropic.
   Where no secure storage exists it is kept for that run only and the dialog says so. Anthropic bills the key's owner
   directly. **Remove key** goes back to the second way.
2. **Azure / Microsoft Foundry**, set up in a `.env` file or the environment (see *Try it (terminal)* for the variables).
   A key saved in Settings is used instead of a Foundry setup while it exists.

The same engine reads `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` from the environment when no Foundry endpoint is set
(handy for the terminal command); a key saved in Settings wins over them.

## Build the Windows app

On Windows, from the project folder:

```powershell
uv sync --locked
uv run --group build pyinstaller packaging/excel-filler.spec
```

The result is `dist\ExcelFiller\ExcelFiller.exe` with its `_internal` folder: zip the whole `ExcelFiller` folder to share it.
If the window does not open, read the newest file in `%USERPROFILE%\.coding-agent\logs`. The recipe is untested on a clean
PC: check that it starts on a machine without Python, and that the saved key survives a restart.

## Try it (terminal)

```bash
uv sync
uv run comptaia -d path/to/folder costs.xlsx invoice1.pdf invoice2.pdf -n "amounts excl. VAT, one row per line item"
```

Configuration (environment variables or a `.env` file in the folder you run from). The terminal command has no
Settings screen: it uses these.

| Variable | Meaning |
|---|---|
| `ANTHROPIC_API_KEY` | your Anthropic API key (used when no Foundry endpoint is set) |
| `ANTHROPIC_MODEL` | a model ID (default `claude-opus-5`) |
| `ANTHROPIC_FOUNDRY_ENDPOINT` | `https://<resource>.services.ai.azure.com/anthropic` (Foundry; wins over `ANTHROPIC_API_KEY`) |
| `ANTHROPIC_FOUNDRY_API_KEY` | Foundry API key; leave unset to sign in with your Microsoft work account (below) |
| `ANTHROPIC_FOUNDRY_DEPLOYMENT` | your Claude deployment name (Foundry) |

**Signing in** (no API key): nothing to install or type. On a company Windows PC the app uses the
account signed into Windows. Otherwise the Microsoft sign-in page opens in the browser, once; the
account is remembered and later launches sign in silently. Developers' `az login` also works. The
account needs access to the Foundry resource (a role such as *Azure AI User*, granted by IT).
Optional: `AZURE_TENANT_ID` (the resource's tenant, if not your account's) and `AZURE_CLIENT_ID`
(your organization's app registration for the sign-in page).

**Auto mode** (the switch above *Fill workbook*, or `comptaia --auto`): changes are saved without
asking and Claude's questions are not asked; missing or ambiguous values are left empty and listed at
the end. A workbook with features that saving would damage still asks first.

A copy of the previous version of every workbook it saves is kept in `~/.coding-agent/backups/`.

## Versions

Every dependency is pinned to the exact version it was tested with: Python packages in
`pyproject.toml` (and all their own dependencies in `uv.lock`), the agent engine to a commit of
DemePS/CodeAgent, and the UI's packages in `frontend/package.json` (and `package-lock.json`). Install
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

They run a whole filling job against a mocked Claude API through the real SDK and tools, and the Settings
endpoints (a failing key test saves nothing, the key never appears in a reply, the log or an error, a saved key is
applied at startup).

## Roadmap

1. ~~Agent engine as a package (`coding_agent`), imported here~~
2. ~~Desktop window: pick a folder, a workbook and documents; watch progress; approve cell
   changes and answer questions in the window.~~
3. ~~Claude access: your Anthropic API key (kept in the Windows Credential Manager) or Azure / Foundry.~~
4. ~~A PyInstaller recipe for the Windows app~~ (written, not yet run on a clean Windows PC).
5. Windows installer, built by CI, and code signing.
6. Selling it: licence activation, terms, a website.
