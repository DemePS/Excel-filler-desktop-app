// Events sent by the backend (excel_filler/desktop/webui.py), one per UI call of the agent.

export type CellRow = { cell: string; old: string; new: string; format: string | null }

export type AgentEvent =
  | { type: 'status' | 'success' | 'failure' | 'warning' | 'message' | 'error'; text: string }
  | { type: 'panel'; title: string; lines: string[]; tone: string }
  | { type: 'diff'; action: string; name: string; path: string; first_line: number; lines: string[] }
  | { type: 'cells'; title: string; rows: CellRow[]; more: number }
  | { type: 'confirm'; id: string; question: string; choices: string[] }
  | { type: 'ask'; id: string; prompt: string; multiline: boolean }
  | { type: 'answered'; id: string }
  | { type: 'assistant_start' | 'assistant_end' | 'thinking' }
  | { type: 'text'; text: string }
  | { type: 'request'; text: string }
  | { type: 'tool'; name: string }
  | { type: 'tool_detail'; text: string }
  | { type: 'tool_result'; name: string; arguments: string; ok: boolean; summary: string }
  | { type: 'busy'; busy: boolean }
  | ({ type: 'listing' } & Listing)

export type Listing = { folder: string | null; workbooks: string[]; documents: string[]; workbook: string | null }

export type Hello = Listing & {
  type: 'hello'
  history: AgentEvent[]
  busy: boolean
  connection_problem: string | null
}

// What the activity feed shows.
export type Item =
  | { kind: 'claude'; text: string }
  | { kind: 'you'; text: string }
  | { kind: 'step'; label: string; detail: string; failed?: string }
  | { kind: 'note'; tone: 'status' | 'success' | 'failure' | 'warning' | 'message' | 'error'; text: string }
  | { kind: 'change'; event: Extract<AgentEvent, { type: 'panel' | 'diff' | 'cells' }> }

export type Question =
  | { kind: 'confirm'; id: string; question: string; choices: string[]; context: Item | null }
  | { kind: 'ask'; id: string; prompt: string; multiline: boolean; context: string | null }
