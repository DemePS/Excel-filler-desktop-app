# Excel filler (API Management edition)

Fill an Excel workbook from PDF documents with Claude (Azure / Microsoft Foundry), reviewing
every change before it is saved.

This branch, `api-management`, is the version the organization gives to its employees: the app
reaches Claude only through the organization's **Azure API Management gateway**.

- **Access:** employees sign in with their work account (silently, with the account signed into
  Windows). Only members of the "Excel filler users" Entra ID group get in; the app checks it at
  startup and explains a refusal in plain words. No key or secret is ever on a PC.
- **Central settings:** the Claude deployment, the oldest allowed app version and a message for all
  users are read from the gateway at startup; IT changes them without reinstalling anything.
- **Limits and monitoring:** per-user limits, and who uses it with which app version, in the
  gateway (never the content of documents or answers).
- **Distribution:** a Windows zip built by `azure-pipelines.yml`, with the organization's gateway
  settings built in, signed with Azure Trusted Signing.

| For | Read |
|---|---|
| IT: deploying the gateway, Entra ID setup, the build | [`infra/README.md`](infra/README.md) |
| Code signing | [`docs/code-signing.md`](docs/code-signing.md) |
| The rollout proposal | [`docs/enterprise-deployment-proposal.md`](docs/enterprise-deployment-proposal.md) |

## Using it


You open the workbook and pick the documents (invoices, statements, scans): those next to the
workbook, the documents of another folder instead (**Change folder…**; **Use the workbook's folder**
goes back), more folders (**Add folder…**), or single files from anywhere (**Add files…**). Folders outside the workbook's are read-only for the agent, which only
ever writes the workbook. It
opens the workbook first to see which fields are needed, reads only the document pages that hold
them, writes the values (you approve a cell-by-cell diff), checks them, and ends with the source
of every value. It never invents a value: missing or ambiguous ones are asked or left empty.

## How it is built

The agent engine is the `codeagent-apim`
package (the `coding_agent` package: agent loop, tools, safety rules, memory, context management), installed as a dependency.
This project only adds:

| | |
|---|---|
| `excel_filler/agent.py` | the tools Claude gets (read documents, read/write the workbook, ask you; no code execution, deletion or network), its instructions, and how a job is phrased |
| `excel_filler/cli.py` | the `excel-filler` terminal command |
| `excel_filler/desktop/` | the desktop window: a local FastAPI backend (127.0.0.1, per-launch token) running the agent in a worker thread, `WebUI` sending the agent's UI calls to the window over a WebSocket, and `app.py` opening a native window (pywebview) |
| `frontend/` | the window's React UI: choose a folder, pick the workbook and documents, watch the work, approve cell changes, answer Claude's questions, ask for corrections |

## Gateway settings

The organization's values are built into the app by the pipeline (`excel_filler/organization.json`,
from the variable group `excel-filler`); environment variables override them:

| Variable | Meaning |
|---|---|
| `EXCEL_FILLER_GATEWAY` | the gateway, `https://<apim>.azure-api.net/excel-filler` |
| `EXCEL_FILLER_API_SCOPE` | `api://<gateway API app id>/.default` |
| `EXCEL_FILLER_CLIENT_ID` | the desktop app registration employees sign in with |
| `EXCEL_FILLER_TENANT_ID` | the organization's tenant |

Without them (the file in the repository is empty) the app is a **developer build**: no access
check, and Claude is called directly on Foundry with the settings under *Try it* below.

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
| `ANTHROPIC_FOUNDRY_API_KEY` | API key; leave unset to sign in with your Microsoft work account (below) |
| `ANTHROPIC_FOUNDRY_DEPLOYMENT` | your Claude deployment name |

**Signing in** (no API key): nothing to install or type. On a company Windows PC the app uses the
account signed into Windows. Otherwise the Microsoft sign-in page opens in the browser, once; the
account is remembered and later launches sign in silently. Developers' `az login` also works. The
account needs access to the Foundry resource (a role such as *Azure AI User*, granted by IT).
Optional: `AZURE_TENANT_ID` (the resource's tenant, if not your account's) and `AZURE_CLIENT_ID`
(your organization's app registration for the sign-in page).

**Auto mode** (the switch above *Fill workbook*, or `excel-filler --auto`): changes are saved without
asking and Claude's questions are not asked; missing or ambiguous values are left empty and listed at
the end. A workbook with features that saving would damage still asks first.

A copy of the previous version of every workbook it saves is kept in `~/.coding-agent/backups/`.

## Versions

Every dependency is pinned to the exact version it was tested with: Python packages in
`pyproject.toml` (and all their own dependencies in `uv.lock`), the agent engine as
`codeagent-apim==0.1.0` (taken from a commit of DemePS/CodeAgent until it is on PyPI: see
`[tool.uv.sources]` in `pyproject.toml`), and the UI's packages in `frontend/package.json` (and `package-lock.json`). Install
exactly those with:

```bash
uv sync --locked          # fails instead of changing a version if uv.lock is out of date
cd frontend && npm ci     # only to change the UI
```

To upgrade something (for example the engine: its version, and its source in `[tool.uv.sources]`), change its version, run `uv lock` (or `npm install` in `frontend/`), run the tests, and commit the lock file.

## Tests

```bash
uv run pytest -q
```

They run a whole filling job against a mocked Claude API through the real SDK and tools.

## Roadmap

1. ~~Agent engine as a package (`codeagent-apim`), imported here~~
2. ~~Desktop window: pick a folder, a workbook and documents; watch progress; approve cell
   changes and answer questions in the window.~~
3. ~~Sign-in with the work account; access through the API Management gateway~~
4. ~~Windows build, self-test and signing on Azure Pipelines~~
5. Deploy the gateway and the Entra ID setup (`infra/README.md`), then a pilot with a few users.
