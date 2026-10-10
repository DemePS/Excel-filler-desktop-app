// Turns the agent's events into what the window shows: an activity feed and the open question.

import type { AgentEvent, CellRow, Item, Listing, Question } from './types'

export type State = {
  items: Item[]
  question: Question | null
  busy: boolean
  listing: Listing
  auto: boolean // auto mode: changes applied without asking
  problem: string | null
  lastChange: Item | null // shown with the next approval question
  lastAsked: string | null // Claude's question, shown with the next text question
  activity: string // what Claude is doing right now, shown while a job runs
}

export const initialState: State = {
  items: [],
  question: null,
  busy: false,
  listing: { folder: null, workbooks: [], documents: [], workbook: null, documents_folder: null },
  auto: false,
  problem: null,
  lastChange: null,
  lastAsked: null,
  activity: '',
}

// Text from an event, whatever the backend sent (never undefined or an object, which would break the page).
const text = (value: unknown) => (typeof value === 'string' ? value : value == null ? '' : String(value))

// Progress lines meant for the terminal, not for the window.
const TECHNICAL_STATUS = /^\[(context|memory|excel|pdf|image|cwd|skill)\]/

// What each tool does, in plain words.
const TOOL_LABELS: Record<string, string> = {
  read_excel: 'Reading the workbook',
  edit_excel: 'Preparing changes to the workbook',
  read_pdf: 'Reading a document',
  view_image: 'Looking at an image',
  read_file: 'Reading a file',
  list_directory: 'Looking at the folder',
  ask_human: 'Asking you a question',
}

export function answered(state: State, text: string): State {
  return text.trim() ? { ...state, items: [...state.items, { kind: 'you', text: text.trim() }] } : state
}

// Cells of a change, for a step: "A32 = 45.50, B32 = 12" (the first few).
function cellsSummary(rows: CellRow[], more: number): string {
  const shown = rows.slice(0, 4).map((r) => `${r.cell.replace(/^.*!/, '')} = ${text(r.new) || 'empty'}`)
  const rest = rows.length - shown.length + more
  // The sheet once, when all the cells are in the same one: "sheet Costs: A32 = 45.50, B32 = 12".
  const sheets = [...new Set(rows.map((r) => (r.cell.includes('!') ? r.cell.slice(0, r.cell.lastIndexOf('!')) : '')))]
  const sheet = sheets.length === 1 && sheets[0] ? `sheet ${sheets[0]}: ` : ''
  return sheet + shown.join(', ') + (rest > 0 ? ` and ${rest} more` : '')
}

// An argument of a tool call as shown in its summary: key='value' (or key="value" when the value
// contains a quote).
function argument(summary: string, key: string): string | undefined {
  const match = new RegExp(`\\b${key}=(?:'([^']*)'|"([^"]*)")`).exec(summary)
  return match ? (match[1] ?? match[2]) : undefined
}

// What a tool works on: the file, and for a workbook its sheet and range, for a PDF its pages.
export function toolTarget(summary: string): string {
  const file = argument(summary, 'path')
  if (!file) return ''
  const sheet = argument(summary, 'sheet')
  const range = argument(summary, 'range')
  const pages = argument(summary, 'pages')
  return [file, sheet && `sheet ${sheet}`, range, pages && `page ${pages}`].filter(Boolean).join(', ')
}

// A step's plain-words description while it runs: "Reading invoice.pdf, page 2".
function doing(label: string, detail: string): string {
  return detail ? `${label}: ${detail}` : label
}

export function apply(state: State, event: AgentEvent): State {
  const next = applyEvent(state, event)
  const activity = activityOf(next, event)
  return activity === null || activity === next.activity ? next : { ...next, activity }
}

// What the "working" line says after an event (null: unchanged).
function activityOf(state: State, event: AgentEvent): string | null {
  const last = state.items[state.items.length - 1]
  switch (event.type) {
    case 'busy':
      return event.busy ? 'Starting: the assistant receives the workbook and the documents…' : ''
    case 'thinking':
      return 'The assistant is thinking…'
    case 'assistant_start':
    case 'text':
      return 'The assistant is writing…'
    case 'tool':
    case 'tool_detail':
      return last?.kind === 'step' ? doing(last.label, last.detail) + '…' : null
    case 'cells':
      return `Waiting for your approval: ${cellsSummary(event.rows ?? [], event.more ?? 0)}`
    case 'confirm':
      return state.activity.startsWith('Waiting for your approval') ? null : 'Waiting for your approval…'
    case 'ask':
      return 'Waiting for your answer…'
    case 'answered':
    case 'tool_result':
      return 'The assistant is looking at the result…'
    case 'assistant_end':
      // The tool Claude asked for runs now: keep saying what it does.
      return last?.kind === 'step' ? null : 'The assistant is working…'
    default:
      return null
  }
}

function applyEvent(state: State, event: AgentEvent): State {
  const items = state.items
  const last = items[items.length - 1]
  switch (event.type) {
    case 'assistant_start':
      return { ...state, items: [...items, { kind: 'claude', text: '' }] }
    case 'text':
      if (last?.kind === 'claude') return { ...state, items: [...items.slice(0, -1), { ...last, text: last.text + text(event.text) }] }
      return { ...state, items: [...items, { kind: 'claude', text: text(event.text) }] }
    case 'auto':
      return { ...state, auto: event.on }
    case 'saved':
      return { ...state, items: [...items, { kind: 'saved', name: event.name, path: event.path, backups: event.backups }] }
    case 'request':
      return answered(state, text(event.text))
    case 'tool':
      return { ...state, items: [...items, { kind: 'step', label: TOOL_LABELS[event.name] ?? event.name, detail: '' }] }
    case 'tool_detail': {
      // What the tool works on, in plain words: "costs.xlsx, sheet Costs, A1:F40", "invoice.pdf, page 2".
      const detail = toolTarget(text(event.text))
      if (last?.kind === 'step' && detail) {
        return { ...state, items: [...items.slice(0, -1), { ...last, detail }] }
      }
      return state
    }
    case 'tool_result': {
      // A tool that failed: shown on its step (Claude usually corrects itself and tries again).
      if (event.ok) return state
      const i = items.map((item) => item.kind).lastIndexOf('step')
      if (i < 0) return state
      const step = items[i] as Extract<Item, { kind: 'step' }>
      return { ...state, items: [...items.slice(0, i), { ...step, failed: text(event.summary) || 'failed' }, ...items.slice(i + 1)] }
    }
    case 'status':
      if (TECHNICAL_STATUS.test(text(event.text))) return state
      return { ...state, items: [...items, { kind: 'note', tone: 'status', text: text(event.text) }] }
    case 'message':
      if (text(event.text) === '[interrupted]') return { ...state, items: [...items, { kind: 'note', tone: 'warning', text: 'Stopped.' }] }
      return { ...state, items: [...items, { kind: 'note', tone: 'message', text: text(event.text) }] }
    case 'warning':
      // The engine's auto mode announcement is written for its terminal (Ctrl+C, /auto): the switch
      // and the "Auto mode" tag already say it here.
      if (/^Autonomous mode (ON|OFF)/.test(text(event.text))) return state
      return { ...state, items: [...items, { kind: 'note', tone: 'warning', text: text(event.text) }] }
    case 'success':
    case 'failure':
    case 'error':
      return { ...state, items: [...items, { kind: 'note', tone: event.type, text: text(event.text) }] }
    case 'panel':
      if (event.tone === 'question') return { ...state, lastAsked: event.title }
      return withChange(state, { kind: 'change', event })
    case 'cells': {
      // The step that prepared these changes says which cells: "costs.xlsx: A32 = 45.50, B32 = 12".
      const i = items.map((item) => item.kind).lastIndexOf('step')
      const step = i >= 0 ? (items[i] as Extract<Item, { kind: 'step' }>) : null
      const cells = cellsSummary(event.rows ?? [], event.more ?? 0)
      const withCells = step && cells
        ? { ...state, items: [...items.slice(0, i), { ...step, label: 'Filling cells', detail: `${step.detail ? step.detail + ', ' : ''}${cells}` }, ...items.slice(i + 1)] }
        : state
      return withChange(withCells, { kind: 'change', event })
    }
    case 'diff':
      return withChange(state, { kind: 'change', event })
    case 'confirm':
      return { ...state, question: { kind: 'confirm', id: event.id, question: event.question, choices: event.choices, context: state.lastChange } }
    case 'ask': {
      // Keep Claude's question in the feed; the answer is added when you send it.
      const asked: Item[] = state.lastAsked ? [{ kind: 'claude', text: state.lastAsked }] : []
      return { ...state, items: [...items, ...asked], question: { kind: 'ask', id: event.id, prompt: event.prompt, multiline: event.multiline, context: state.lastAsked }, lastAsked: null }
    }
    case 'answered':
      return state.question?.id === event.id ? { ...state, question: null } : state
    case 'busy':
      return { ...state, busy: event.busy, lastChange: event.busy ? null : state.lastChange }
    case 'listing':
      return { ...state, listing: { folder: event.folder, workbooks: event.workbooks, documents: event.documents, workbook: event.workbook, documents_folder: event.documents_folder ?? null } }
    default:
      return state
  }
}

function withChange(state: State, item: Item): State {
  return { ...state, items: [...state.items, item], lastChange: item }
}
