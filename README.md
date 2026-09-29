# Excel-filler-desktop-app

Desktop application for the coding agent: Claude on Azure (Microsoft Foundry) with a
manual tool-use loop, file edits behind diff approvals, sandboxed Python runs, skills, memory,
PDF/Excel tools and page screenshots.

This project starts as a copy of the terminal agent (`agent.py`, `skills/`) from
DemePS/weather, branch `claude/coding-agent-tools-8dvdd2`, commit `9f17a52`. That terminal agent
keeps living there; this repository adapts it into a desktop application.

## Run the terminal agent (current state)

```bash
uv sync --extra browser
uv run coding-agent -d path/to/project
uv run coding-agent --where          # where memory and skills are read from
uv run coding-agent --check-browser  # test the browser used for screenshots
```

Configuration (environment variables or a `.env` file):

| Variable | Meaning |
|---|---|
| `ANTHROPIC_FOUNDRY_ENDPOINT` | `https://<resource>.services.ai.azure.com/anthropic` |
| `ANTHROPIC_FOUNDRY_API_KEY` | API key; leave unset to sign in with Azure AD |
| `ANTHROPIC_FOUNDRY_DEPLOYMENT` | your Claude deployment name |

See the docstring at the top of `agent.py` for every tool, setting and safety rule.

## Roadmap

1. Split `agent.py` into a core (loop, tools, safety rules) and a UI layer (terminal today).
2. Desktop UI: React front end + local FastAPI backend in a native window.
3. Microsoft sign-in (Entra ID) to the organization's Foundry deployment.
4. Installers built by CI, code signing, auto-update.
