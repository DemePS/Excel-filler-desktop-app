import type { Listing, SettingsInfo, Sheet } from './types'

// Talking to the local backend. Every request carries the per-launch token from the page URL.

const token = new URLSearchParams(window.location.search).get('token') ?? ''

async function call<T>(path: string, body?: unknown, method?: string): Promise<T> {
  const response = await fetch(path, {
    method: method ?? (body === undefined ? 'GET' : 'POST'),
    headers: { 'content-type': 'application/json', 'x-token': token },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error((data as { detail?: string }).detail ?? `Error ${response.status}`)
  return data as T
}

export const api = {
  openFolder: (path: string) => call('/api/folder', { path }),
  openWorkbook: (path: string) => call('/api/workbook', { path }),
  addDocuments: (paths: string[]) => call('/api/documents', { paths }),
  addDocumentFolder: (path: string) => call<Listing & { added: string[] }>('/api/document-folder', { path }),
  changeDocumentFolder: (path: string) => call<Listing & { added: string[] }>('/api/document-folder/change', { path }),
  resetDocumentFolder: () => call<Listing>('/api/document-folder/reset', {}),
  startJob: (workbook: string, documents: string[], notes: string, sheets: string[], copy: boolean, language: string) =>
    call<{ started: boolean; workbook: string }>('/api/job', { workbook, documents, notes, sheets, on_copy: copy, language }),
  sheets: (workbook: string) => call<{ sheets: Sheet[] }>(`/api/sheets?workbook=${encodeURIComponent(workbook)}`),
  followUp: (text: string, language: string) => call('/api/followup', { text, language }),
  answer: (id: string, value: string | null) => call('/api/answer', { id, value }),
  stop: () => call('/api/stop', {}),
  setAuto: (on: boolean) => call<{ auto: boolean }>('/api/auto', { on }),
  openInExcel: (name: string) => call('/api/open', { text: name }),
  getSettings: () => call<SettingsInfo>('/api/settings'),
  saveSettings: (api_key: string, model: string) => call<SettingsInfo>('/api/settings', { api_key, model }),
  removeKey: () => call<SettingsInfo>('/api/settings/key', undefined, 'DELETE'),
  check: () => call<{ ok: boolean; message: string }>('/api/check'),
}

// Sends an error of the window's code to the backend, which writes it to the log file.
export function reportError(message: string, stack?: string) {
  fetch('/api/client-error', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-token': token },
    body: JSON.stringify({ message: message || 'Unknown error', stack: stack ?? null }),
  }).catch(() => {})
}

export function connectEvents(onEvent: (event: unknown) => void, onClose: () => void): WebSocket {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${scheme}://${window.location.host}/ws?token=${encodeURIComponent(token)}`)
  ws.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data))
    } catch (e) {
      reportError(`Could not handle an event: ${(e as Error).message}`, String(message.data).slice(0, 2000))
    }
  }
  ws.onclose = onClose
  return ws
}

// In the desktop window, pywebview exposes the native Windows file dialogs.
type PyWebview = {
  api: {
    pick_workbook: () => Promise<string | null>
    pick_chart: () => Promise<string | null>
    pick_documents: (folder: string) => Promise<string[]>
    pick_document_folder: (folder: string) => Promise<string | null>
    open_external: (url: string) => Promise<boolean>
  }
}

const native = () => (window as unknown as { pywebview?: PyWebview }).pywebview

// In a browser (no native window) the backend, which runs on this machine, can open the system's dialog
// (Linux: zenity). When it cannot, the person types the path.
async function backendDialog(kind: 'workbook' | 'documents' | 'folder' | 'chart', folder?: string): Promise<string[] | null> {
  try {
    const info = await call<{ available: boolean }>('/api/pick/available')
    if (!info.available) return null
    return (await call<{ paths: string[] }>('/api/pick', { kind, folder })).paths
  } catch {
    return null
  }
}

export async function pickWorkbook(): Promise<string | null> {
  const pywebview = native()
  if (pywebview) return pywebview.api.pick_workbook()
  const chosen = await backendDialog('workbook')
  if (chosen) return chosen[0] ?? null
  return window.prompt('Full path of the Excel workbook to fill (.xlsx or .xlsm):')
}

export async function pickChart(): Promise<string | null> {
  const pywebview = native()
  if (pywebview) return pywebview.api.pick_chart()
  const chosen = await backendDialog('chart')
  if (chosen) return chosen[0] ?? null
  return window.prompt('Full path of the chart of accounts (PDF or text):')
}

export type ChartInfo = { file: string | null; folder: string; modified: number | null }
export const getChart = () => call<ChartInfo>('/api/chart-of-accounts')
export const updateChart = (path: string) => call<ChartInfo>('/api/chart-of-accounts', { path })

export async function pickDocuments(folder: string): Promise<string[]> {
  const pywebview = native()
  if (pywebview) return pywebview.api.pick_documents(folder)
  const chosen = await backendDialog('documents', folder)
  if (chosen) return chosen
  const answer = window.prompt(`Full paths of the documents, one per line or separated by ";" (they must be in ${folder}):`)
  return answer ? answer.split(/[;\n]/).map((p) => p.trim()).filter(Boolean) : []
}

export async function pickDocumentFolder(folder: string): Promise<string | null> {
  const pywebview = native()
  if (pywebview) return pywebview.api.pick_document_folder(folder)
  const chosen = await backendDialog('folder', folder)
  if (chosen) return chosen[0] ?? null
  return window.prompt('Full path of the folder holding the documents, or of any document in it:')
}

export const KEYS_URL = 'https://console.anthropic.com/settings/keys'

// A link in the window would replace the app itself: the desktop window opens it in the browser.
export async function openExternal(url: string): Promise<boolean> {
  const pywebview = native()
  if (pywebview) return pywebview.api.open_external(url)
  window.open(url, '_blank', 'noopener')
  return true
}

export const hasNativeWindow = () => native() !== undefined
