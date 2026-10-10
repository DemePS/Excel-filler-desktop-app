import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { api, connectEvents, pickDocumentFolder, pickDocuments, pickWorkbook } from './api'
import { Activity } from './components/Activity'
import { JobPanel } from './components/JobPanel'
import { QuestionDialog } from './components/QuestionDialog'
import { SettingsDialog } from './components/SettingsDialog'
import { Splitter, useSidebarWidth } from './components/Splitter'
import { answered, apply, initialState, type State } from './state'
import type { AgentEvent, Hello, Listing, SettingsInfo } from './types'

type Action = { kind: 'problem'; problem: string | null } | { kind: 'event'; event: AgentEvent } | { kind: 'hello'; hello: Hello } | { kind: 'reset' } | { kind: 'you'; text: string }

function reducer(state: State, action: Action): State {
  if (action.kind === 'problem') return { ...state, problem: action.problem }
  if (action.kind === 'reset') return { ...state, items: [], lastChange: null, activity: '' }
  if (action.kind === 'you') return answered(state, action.text)
  if (action.kind === 'hello') {
    // A (re)connection: rebuild everything from the history the backend kept.
    const { history, busy, connection_problem, folder, workbooks, documents, workbook, documents_folder } = action.hello
    const rebuilt = history.reduce(apply, { ...initialState })
    return { ...rebuilt, busy, auto: action.hello.auto ?? false, problem: connection_problem, listing: { folder, workbooks, documents, workbook, documents_folder } }
  }
  return apply(state, action.event)
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [followUp, setFollowUp] = useState('')
  const [stopping, setStopping] = useState(false)  // Stop pressed; the job ends in a moment
  const [sidebarWidth, setSidebarWidth] = useSidebarWidth()
  const [claude, setClaude] = useState<{ state: 'checking' | 'ok' | 'failed'; message: string }>({ state: 'checking', message: '' })

  const checkConnection = useCallback(async () => {
    setClaude({ state: 'checking', message: '' })
    try {
      const result = await api.check()
      setClaude({ state: result.ok ? 'ok' : 'failed', message: result.message })
    } catch (e) {
      setClaude({ state: 'failed', message: (e as Error).message })
    }
  }, [])
  useEffect(() => { if (connected) checkConnection() }, [connected, checkConnection])

  // Settings: the API key. Nothing is set up yet (first run): the dialog opens by itself and cannot be skipped.
  const [settings, setSettings] = useState<SettingsInfo | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  useEffect(() => {
    if (!connected) return
    api.getSettings().then((info) => { setSettings(info); if (!info.configured) setSettingsOpen(true) }).catch(() => {})
  }, [connected])
  const settingsChanged = (info: SettingsInfo) => {
    setSettings(info)
    setSettingsOpen(!info.configured)
    dispatch({ kind: 'problem', problem: info.configured ? null : 'Add your Anthropic API key in Settings to start.' })
    checkConnection()
  }

  useEffect(() => {
    let ws: WebSocket | null = null
    let retry: number | undefined
    const connect = () => {
      ws = connectEvents(
        (data) => {
          const event = data as AgentEvent | Hello
          if (event.type === 'hello') {
            setConnected(true)
            dispatch({ kind: 'hello', hello: event as Hello })
          } else {
            // Claude is answering: it is reachable, whatever the startup check says (or has not said yet).
            if (['assistant_start', 'text', 'thinking', 'tool'].includes(event.type)) {
              setClaude((c) => (c.state === 'ok' ? c : { state: 'ok', message: 'Claude answered' }))
            }
            dispatch({ kind: 'event', event: event as AgentEvent })
          }
        },
        () => {
          setConnected(false)
          retry = window.setTimeout(connect, 1000)
        },
      )
    }
    connect()
    return () => {
      window.clearTimeout(retry)
      if (ws) {
        ws.onclose = null
        ws.close()
      }
    }
  }, [])

  const run = useCallback(async (action: () => Promise<unknown>) => {
    setError(null)
    try {
      await action()
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  const openWorkbook = () =>
    run(async () => {
      const path = await pickWorkbook()
      if (path) {
        dispatch({ kind: 'reset' })
        const listing = (await api.openWorkbook(path)) as Listing
        dispatch({ kind: 'event', event: { type: 'listing', ...listing } })
      }
    })

  // Documents from a folder of their own: the job uses those (ticked), not the ones next to the workbook.
  const [selection, setSelection] = useState<{ documents: string[] } | null>(null)
  const addDocumentFolder = () =>
    run(async () => {
      if (!state.listing.folder) return
      const path = await pickDocumentFolder(state.listing.folder)
      if (path) {
        const result = await api.addDocumentFolder(path)
        dispatch({ kind: 'event', event: { type: 'listing', folder: result.folder, workbooks: result.workbooks, documents: result.documents, workbook: result.workbook, documents_folder: result.documents_folder } })
        setSelection({ documents: result.added })
      }
    })

  // Documents from another folder instead: only that folder's documents are listed (and ticked).
  const changeDocumentFolder = () =>
    run(async () => {
      if (!state.listing.folder) return
      const path = await pickDocumentFolder(state.listing.documents_folder ?? state.listing.folder)
      if (path) {
        const result = await api.changeDocumentFolder(path)
        dispatch({ kind: 'event', event: { type: 'listing', folder: result.folder, workbooks: result.workbooks, documents: result.documents, workbook: result.workbook, documents_folder: result.documents_folder } })
        setSelection({ documents: result.added })
      }
    })

  const resetDocumentFolder = () =>
    run(async () => {
      const listing = await api.resetDocumentFolder()
      dispatch({ kind: 'event', event: { type: 'listing', ...listing } })
    })

  const addDocuments = () =>
    run(async () => {
      if (!state.listing.folder) return
      const paths = await pickDocuments(state.listing.folder)
      if (paths.length) {
        const listing = (await api.addDocuments(paths)) as Listing
        dispatch({ kind: 'event', event: { type: 'listing', ...listing } })
      }
    })

  const { listing, busy, question } = state
  useEffect(() => { if (!busy) setStopping(false) }, [busy])
  // Claude ended with a question (instead of asking it in a dialog): the reply box says so and takes the focus.
  const lastClaude = [...state.items].reverse().find((item) => item.kind === 'claude' ? item.text.trim() : item.kind !== 'note')
  const awaitingReply = !busy && !question && lastClaude?.kind === 'claude' && lastClaude.text.trim().endsWith('?')
  const reply = useRef<HTMLInputElement>(null)
  useEffect(() => { if (awaitingReply) reply.current?.focus() }, [awaitingReply])
  return (
    <div className="app">
      <header>
        <div className="brand"><span className="logo" aria-hidden /> Excel filler</div>
        <div className="folder" title={listing.folder ?? ''}>{listing.folder ?? 'No workbook open'}</div>
        {/* Nothing while the startup check runs: only its result (connected, or an error). */}
        {state.auto && <span className="auto-tag" title="Changes are applied without asking; a backup of the workbook is kept">Auto mode</span>}
        {claude.state !== 'checking' && !state.problem && (
          <span className={`claude-status ${claude.state}`} title={claude.message}>
            {claude.state === 'ok' ? 'Claude connected' : 'Claude unreachable'}
          </span>
        )}
        <button onClick={() => setSettingsOpen(true)} disabled={busy || !settings} title="Anthropic API key and model">Settings</button>
        <button className={listing.folder ? '' : 'primary'} onClick={openWorkbook} disabled={busy || !!state.problem}>
          {listing.folder ? 'Open another workbook…' : 'Open workbook…'}
        </button>
      </header>

      {!connected && <div className="banner warning">Connecting to the agent…</div>}
      {claude.state === 'failed' && !state.problem && (
        <div className="banner error" role="alert">
          <b>Claude cannot be reached.</b> {claude.message}
          <button className="link" onClick={checkConnection}>Retry</button>
        </div>
      )}
      {error && <div className="banner error" role="alert">{error}<button className="link" onClick={() => setError(null)}>Dismiss</button></div>}

      <main style={{ gridTemplateColumns: `${sidebarWidth}px auto minmax(0, 1fr)` }}>
        <JobPanel listing={listing} busy={busy} auto={state.auto} onAuto={(on) => run(() => api.setAuto(on))} onAddDocuments={addDocuments} onAddDocumentFolder={addDocumentFolder}
          onChangeDocumentFolder={changeDocumentFolder} onResetDocumentFolder={resetDocumentFolder} selection={selection}
          onFill={(workbook, documents, notes, sheets, copy) => run(() => { dispatch({ kind: 'reset' }); return api.startJob(workbook, documents, notes, sheets, copy) })} />
        <Splitter width={sidebarWidth} onResize={setSidebarWidth} />
        <section className="feed">
          <Activity items={state.items} busy={busy} activity={stopping ? 'Stopping…' : state.activity} onOpen={(name) => run(() => api.openInExcel(name))} />
          {awaitingReply && <div className="reply-hint" role="status">Claude asked you a question: answer it below.</div>}
          <form className={`composer${awaitingReply ? ' awaiting' : ''}`} onSubmit={(e) => {
            e.preventDefault()
            if (followUp.trim()) run(async () => { await api.followUp(followUp); setFollowUp('') })
          }}>
            <input ref={reply} placeholder={awaitingReply ? 'Your answer…' : listing.folder ? 'Ask for a correction, e.g. “use the invoice date, not the due date”' : ''}
              value={followUp} onChange={(e) => setFollowUp(e.target.value)} disabled={!listing.folder || busy} aria-label="Follow-up request" />
            {busy
              ? <button type="button" className="danger" disabled={stopping} onClick={() => { setStopping(true); run(api.stop) }}>{stopping ? 'Stopping…' : 'Stop'}</button>
              : <button type="submit" disabled={!followUp.trim()}>Send</button>}
          </form>
        </section>
      </main>

      {settingsOpen && settings && !question && (
        <SettingsDialog info={settings} firstRun={!settings.configured} onClose={() => setSettingsOpen(false)} onChanged={settingsChanged} />
      )}
      {question && <QuestionDialog question={question} onAnswer={(value) => run(async () => {
        await api.answer(question.id, value)
        if (question.kind === 'ask' && value) dispatch({ kind: 'you', text: value })
      })} />}
    </div>
  )
}
