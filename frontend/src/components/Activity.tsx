// The job's activity: Claude's messages, what it is doing, and the changes it made or proposed.

import { useEffect, useRef } from 'react'
import type { Item } from '../types'
import { Change } from './Change'

export function Activity({ items, busy, activity }: { items: Item[]; busy: boolean; activity: string }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => end.current?.scrollIntoView({ block: 'end' }), [items.length, busy, activity])

  const visible = items.filter((item) => item.kind !== 'claude' || item.text.trim())
  if (visible.length === 0 && !busy) {
    return (
      <div className="empty-state">
        <h2>Fill a workbook from your documents</h2>
        <ol>
          <li>Open the workbook to fill. Its folder is where the agent works.</li>
          <li>Tick the documents to use from that folder, or add documents from any folder (read only).</li>
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
            return <div key={i} className="claude">{item.text}</div>
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
          case 'change':
            return <Change key={i} item={item} />
        }
      })}
      {busy && <div className="working" role="status"><span className="spinner" aria-hidden /> {activity || 'Working…'}</div>}
      <div ref={end} />
    </div>
  )
}
