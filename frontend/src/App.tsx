import { useCallback, useEffect, useReducer, useState } from 'react'
import { api, connectEvents, pickFolder } from './api'
import { Activity } from './components/Activity'
import { JobPanel } from './components/JobPanel'
import { QuestionDialog } from './components/QuestionDialog'
import { answered, apply, initialState, type State } from './state'
import type { AgentEvent, Hello, Listing } from './types'

type Action = { kind: 'event'; event: AgentEvent } | { kind: 'hello'; hello: Hello } | { kind: 'reset' } | { kind: 'you'; text: string }

function reducer(state: State, action: Action): State {
  if (action.kind === 'reset') return { ...state, items: [], lastChange: null }
  if (action.kind === 'you') return answered(state, action.text)
  if (action.kind === 'hello') {
    // A (re)connection: rebuild everything from the history the backend kept.
    const { history, busy, connection_problem, folder, workbooks, documents } = action.hello
    const rebuilt = history.reduce(apply, { ...initialState })
    return { ...rebuilt, busy, problem: connection_problem, listing: { folder, workbooks, documents } }
  }
  return apply(state, action.event)
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [followUp, setFollowUp] = useState('')

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
          } else dispatch({ kind: 'event', event: event as AgentEvent })
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

  const chooseFolder = () =>
    run(async () => {
      const path = await pickFolder()
      if (path) {
        dispatch({ kind: 'reset' })
        const listing = (await api.openFolder(path)) as Listing
        dispatch({ kind: 'event', event: { type: 'listing', ...listing } })
      }
    })

  const { listing, busy, question } = state
  return (
    <div className="app">
      <header>
        <div className="brand"><span className="logo" aria-hidden /> Excel filler</div>
        <div className="folder" title={listing.folder ?? ''}>{listing.folder ?? 'No folder chosen'}</div>
        <button onClick={chooseFolder} disabled={busy}>{listing.folder ? 'Change folder' : 'Choose folder'}</button>
      </header>

      {!connected && <div className="banner warning">Connecting to the agent…</div>}
      {state.problem && <div className="banner warning">{state.problem} Ask whoever set up the app, or see the README.</div>}
      {error && <div className="banner error" role="alert">{error}<button className="link" onClick={() => setError(null)}>Dismiss</button></div>}

      <main>
        <JobPanel listing={listing} busy={busy}
          onFill={(workbook, documents, notes) => run(() => { dispatch({ kind: 'reset' }); return api.startJob(workbook, documents, notes) })} />
        <section className="feed">
          <Activity items={state.items} busy={busy} />
          <form className="composer" onSubmit={(e) => {
            e.preventDefault()
            if (followUp.trim()) run(async () => { await api.followUp(followUp); dispatch({ kind: 'you', text: followUp }); setFollowUp('') })
          }}>
            <input placeholder={listing.folder ? 'Ask for a correction, e.g. “use the invoice date, not the due date”' : ''}
              value={followUp} onChange={(e) => setFollowUp(e.target.value)} disabled={!listing.folder || busy} aria-label="Follow-up request" />
            {busy
              ? <button type="button" className="danger" onClick={() => run(api.stop)}>Stop</button>
              : <button type="submit" disabled={!followUp.trim()}>Send</button>}
          </form>
        </section>
      </main>

      {question && <QuestionDialog question={question} onAnswer={(value) => run(async () => {
        await api.answer(question.id, value)
        if (question.kind === 'ask' && value) dispatch({ kind: 'you', text: value })
      })} />}
    </div>
  )
}
