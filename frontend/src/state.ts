// Turns the agent's events into what the window shows: an activity feed and the open question.

import type { AgentEvent, Item, Listing, Question } from './types'

export type State = {
  items: Item[]
  question: Question | null
  busy: boolean
  listing: Listing
  problem: string | null
  lastChange: Item | null // shown with the next approval question
  lastAsked: string | null // Claude's question, shown with the next text question
}

export const initialState: State = {
  items: [],
  question: null,
  busy: false,
  listing: { folder: null, workbooks: [], documents: [], workbook: null },
  problem: null,
  lastChange: null,
  lastAsked: null,
}

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

export function apply(state: State, event: AgentEvent): State {
  const items = state.items
  const last = items[items.length - 1]
  switch (event.type) {
    case 'assistant_start':
      return { ...state, items: [...items, { kind: 'claude', text: '' }] }
    case 'text':
      if (last?.kind === 'claude') return { ...state, items: [...items.slice(0, -1), { ...last, text: last.text + event.text }] }
      return { ...state, items: [...items, { kind: 'claude', text: event.text }] }
    case 'tool':
      return { ...state, items: [...items, { kind: 'step', label: TOOL_LABELS[event.name] ?? event.name, detail: '' }] }
    case 'tool_detail': {
      // Only the file a tool works on is worth showing ("path='costs.xlsx', ..." -> costs.xlsx).
      const file = /path='([^']+)'/.exec(event.text)?.[1]
      const pages = /pages='([^']+)'/.exec(event.text)?.[1]
      if (last?.kind === 'step' && file) {
        return { ...state, items: [...items.slice(0, -1), { ...last, detail: pages ? `${file}, page ${pages}` : file }] }
      }
      return state
    }
    case 'status':
      if (TECHNICAL_STATUS.test(event.text)) return state
      return { ...state, items: [...items, { kind: 'note', tone: 'status', text: event.text }] }
    case 'success':
    case 'failure':
    case 'warning':
    case 'message':
      return { ...state, items: [...items, { kind: 'note', tone: event.type, text: event.text }] }
    case 'panel':
      if (event.tone === 'question') return { ...state, lastAsked: event.title }
      return withChange(state, { kind: 'change', event })
    case 'diff':
    case 'cells':
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
      return { ...state, listing: { folder: event.folder, workbooks: event.workbooks, documents: event.documents, workbook: event.workbook } }
    default:
      return state
  }
}

function withChange(state: State, item: Item): State {
  return { ...state, items: [...state.items, item], lastChange: item }
}
