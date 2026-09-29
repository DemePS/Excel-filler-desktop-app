# Excel filler — window UI

React + TypeScript (Vite). The build goes to `excel_filler/desktop/static/`, which the Python
backend serves to the desktop window.

```bash
npm install
npm run build        # then: uv run excel-filler-desktop
```

The build output is committed, so people who only run the app need no Node.js. After changing
anything here, run `npm run build` and commit `excel_filler/desktop/static/` together with the
source change.

Development with hot reload: start the backend with `uv run excel-filler-desktop --browser`, note
its port, then `BACKEND=http://127.0.0.1:<port> npm run dev` and open the Vite URL with the same
`?token=...` the backend printed.

| File | Role |
|---|---|
| `src/api.ts` | calls to the backend (token on every request), the event WebSocket, the native folder picker |
| `src/state.ts` | turns the agent's events into the activity feed and the open question |
| `src/components/` | job panel, activity feed, change previews (cells, diffs), approval/question dialog |
