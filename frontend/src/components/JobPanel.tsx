// The job: which workbook, which documents, and any instructions.

import { useEffect, useRef, useState } from 'react'
import type { Listing } from '../types'

type Props = {
  listing: Listing
  busy: boolean
  onFill: (workbook: string, documents: string[], notes: string) => void
  onAddDocuments: () => void
}

export function JobPanel({ listing, busy, onFill, onAddDocuments }: Props) {
  const [workbook, setWorkbook] = useState('')
  const [documents, setDocuments] = useState<string[]>([])
  const [notes, setNotes] = useState('')
  const known = useRef<{ folder: string | null; documents: string[] }>({ folder: null, documents: [] })

  // Preselect the workbook that was opened, and tick the documents: all PDFs of a newly opened
  // folder, then every document added afterwards.
  useEffect(() => {
    setWorkbook((current) =>
      listing.workbook && listing.workbooks.includes(listing.workbook) ? listing.workbook
        : listing.workbooks.includes(current) ? current
        : listing.workbooks.length === 1 ? listing.workbooks[0] : '')
    const sameFolder = known.current.folder === listing.folder
    const added = listing.documents.filter((d) => !known.current.documents.includes(d))
    setDocuments((current) => {
      if (!sameFolder) return listing.documents.filter((d) => d.toLowerCase().endsWith('.pdf'))
      return [...current.filter((d) => listing.documents.includes(d)), ...added.filter((d) => !current.includes(d))]
    })
    known.current = { folder: listing.folder, documents: listing.documents }
  }, [listing])

  if (!listing.folder) return <aside className="job"><p className="muted">Open the workbook to fill to start.</p></aside>

  const toggle = (name: string) =>
    setDocuments((current) => (current.includes(name) ? current.filter((d) => d !== name) : [...current, name]))

  return (
    <aside className="job">
      <label htmlFor="workbook">Workbook to fill</label>
      {listing.workbooks.length ? (
        <select id="workbook" value={workbook} onChange={(e) => setWorkbook(e.target.value)}>
          <option value="" disabled>Choose a workbook…</option>
          {listing.workbooks.map((w) => <option key={w}>{w}</option>)}
        </select>
      ) : (
        <p className="muted">No .xlsx or .xlsm file in this folder.</p>
      )}

      <fieldset>
        <legend>Documents to use ({documents.length})</legend>
        {listing.documents.length === 0 && <p className="muted">No PDF or image in this folder yet.</p>}
        <div className="documents">
          {listing.documents.map((d) => (
            <label key={d} className="check">
              <input type="checkbox" checked={documents.includes(d)} onChange={() => toggle(d)} /> <span>{d}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <button onClick={onAddDocuments} disabled={busy}>Add documents…</button>

      <label htmlFor="notes">Instructions <span className="muted">(optional)</span></label>
      <textarea id="notes" rows={4} placeholder="e.g. amounts excluding VAT, one row per line item, dates as dd/mm/yyyy"
        value={notes} onChange={(e) => setNotes(e.target.value)} />

      <button className="primary wide" disabled={busy || !workbook || documents.length === 0}
        onClick={() => onFill(workbook, documents, notes)}>
        Fill workbook
      </button>
    </aside>
  )
}
