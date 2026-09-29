// The job's activity: Claude's messages, what it is doing, and the changes it made or proposed.

import { useEffect, useRef } from 'react'
import type { Item } from '../types'
import { Change } from './Change'
import { Markdown } from './Markdown'

type Props = { items: Item[]; busy: boolean; activity: string; onOpen: (name: string) => void }

export function Activity({ items, busy, activity, onOpen }: Props) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    // A block, not `() => end.current?.scrollIntoView(...)`: newer WebView2/Chromium versions return a
    // Promise from scrollIntoView, which React would then call as the effect's cleanup and crash
    // ("l is not a function", a blank window).
    end.current?.scrollIntoView({ block: 'end' })
  }, [items.length, busy, activity])

  const visible = items.filter((item) => item.kind !== 'claude' || item.text.trim())
  if (visible.length === 0 && !busy) {
    return (
      <div className="empty-state">
        <h2>Fill a workbook from your documents</h2>
        <ol>
          <li>Open the workbook to fill. Its folder is where the agent works.</li>
          <li>Tick the documents to use from that folder, or <b>Add folder…</b> / <b>Add files…</b> if they are elsewhere (read only).</li>
          <li><b>Keep a copy of the workbook</b>: the agent writes into it.</li>
          <li>Press <b>Fill workbook</b>. You approve every change before it is saved.</li>
        </ol>
      </div>
    )
  }
  return (
    <div className="activity" aria-live="polite">
      {visible.map((item, i) => {
        switch (item.kind) {
          case 'claude':
            return <div key={i} className="claude"><Markdown text={item.text} /></div>
          case 'you':
            return <div key={i} className="you">{item.text}</div>
          case 'step':
            return (
              <div key={i} className="step">
                <span className="step-dot" aria-hidden /> {item.label}
                {item.detail && <span className="step-detail"> {item.detail}</span>}
                {item.failed && <div className="step-failed">Did not work: {item.failed}</div>}
              </div>
            )
          case 'note':
            if (item.tone === 'error') return <div key={i} className="error-card" role="alert"><b>Something went wrong.</b> {item.text}</div>
            return <div key={i} className={`note note-${item.tone}`}>{item.tone === 'success' ? '✔ ' : item.tone === 'failure' ? '✘ ' : ''}{item.text}</div>
          case 'saved':
            return (
              <div key={i} className="saved">
                <div>
                  <b>{item.name}</b> is updated.
                  <small title={item.path}>{item.path}</small>
                  <small>The previous version is kept in {item.backups}</small>
                </div>
                <button className="primary" onClick={() => onOpen(item.name)}>Open in Excel</button>
              </div>
            )
          case 'change':
            return <Change key={i} item={item} />
        }
      })}
      {busy && <div className="working" role="status"><span className="spinner" aria-hidden /> {activity || 'Working…'}</div>}
      <div ref={end} />
    </div>
  )
}
