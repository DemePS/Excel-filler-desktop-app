<<<<<<< HEAD
import type { Access, Listing } from './types'
=======
import type { Listing, Sheet } from './types'
>>>>>>> claude/excel-filler-app

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
  openWorkbook: (path: string) => call('/api/workbook', { path }),
  addDocuments: (paths: string[]) => call('/api/documents', { paths }),
  addDocumentFolder: (path: string) => call<Listing & { added: string[] }>('/api/document-folder', { path }),
  startJob: (workbook: string, documents: string[], notes: string, sheets: string[]) => call('/api/job', { workbook, documents, notes, sheets }),
  sheets: (workbook: string) => call<{ sheets: Sheet[] }>(`/api/sheets?workbook=${encodeURIComponent(workbook)}`),
  followUp: (text: string) => call('/api/followup', { text }),
  answer: (id: string, value: string | null) => call('/api/answer', { id, value }),
  stop: () => call('/api/stop', {}),
  openInExcel: (name: string) => call('/api/open', { text: name }),
  check: () => call<{ ok: boolean; message: string }>('/api/check'),
  access: (retry = false) => call<Access>(`/api/access${retry ? '?retry=true' : ''}`),
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
    pick_documents: (folder: string) => Promise<string[]>
    pick_document_folder: (folder: string) => Promise<string | null>
  }
}

const native = () => (window as unknown as { pywebview?: PyWebview }).pywebview

export async function pickWorkbook(): Promise<string | null> {
  const pywebview = native()
  if (pywebview) return pywebview.api.pick_workbook()
  return window.prompt('Full path of the Excel workbook to fill (.xlsx or .xlsm):')
}

export async function pickDocuments(folder: string): Promise<string[]> {
  const pywebview = native()
  if (pywebview) return pywebview.api.pick_documents(folder)
  const answer = window.prompt(`Full paths of the documents, one per line or separated by ";" (they must be in ${folder}):`)
  return answer ? answer.split(/[;\n]/).map((p) => p.trim()).filter(Boolean) : []
}

export async function pickDocumentFolder(folder: string): Promise<string | null> {
  const pywebview = native()
  if (pywebview) return pywebview.api.pick_document_folder(folder)
  return window.prompt('Full path of the folder holding the documents (PDFs, images):')
}
