// Talking to the local backend. Every request carries the per-launch token from the page URL.

const token = new URLSearchParams(window.location.search).get('token') ?? ''

async function call<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'content-type': 'application/json', 'x-token': token },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error((data as { detail?: string }).detail ?? `Error ${response.status}`)
  return data as T
}

export const api = {
  openFolder: (path: string) => call('/api/folder', { path }),
  startJob: (workbook: string, documents: string[], notes: string) => call('/api/job', { workbook, documents, notes }),
  followUp: (text: string) => call('/api/followup', { text }),
  answer: (id: string, value: string | null) => call('/api/answer', { id, value }),
  stop: () => call('/api/stop', {}),
}

export function connectEvents(onEvent: (event: unknown) => void, onClose: () => void): WebSocket {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${scheme}://${window.location.host}/ws?token=${encodeURIComponent(token)}`)
  ws.onmessage = (message) => onEvent(JSON.parse(message.data))
  ws.onclose = onClose
  return ws
}

// In the desktop window, pywebview exposes the native folder picker.
type PyWebview = { api: { pick_folder: () => Promise<string | null> } }

export async function pickFolder(): Promise<string | null> {
  const pywebview = (window as unknown as { pywebview?: PyWebview }).pywebview
  if (pywebview) return pywebview.api.pick_folder()
  return window.prompt('Folder holding the workbook and the documents (full path):')
}
