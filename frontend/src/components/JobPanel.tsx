// The job: which workbook, which documents, and any instructions.

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Listing, Sheet } from '../types'

type Props = {
  listing: Listing
  busy: boolean
  onFill: (workbook: string, documents: string[], notes: string, sheets: string[]) => void
  onAddDocuments: () => void
  onAddDocumentFolder: () => void
  selection: { documents: string[] } | null // documents to tick instead of the current ones
}

// A document in the workbook's folder is shown by its relative path; one from another folder
// (absolute path, read-only for the agent) by its name, with its folder underneath.
function DocumentName({ path }: { path: string }) {
  const absolute = path.startsWith('/') || /^[A-Za-z]:[\\/]/.test(path)
  if (!absolute) return <span>{path}</span>
  const parts = path.split(/[\\/]/)
  return (
    <span className="doc-outside">
      {parts[parts.length - 1]}
      <small>{parts.slice(-3, -1).join('/')} · read only</small>
    </span>
  )
}

export function JobPanel({ listing, busy, onFill, onAddDocuments, onAddDocumentFolder, selection }: Props) {
  const [workbook, setWorkbook] = useState('')
  const [documents, setDocuments] = useState<string[]>([])
  const [notes, setNotes] = useState('')
  const [filter, setFilter] = useState('')
  // The workbook's sheets and the ones to fill (none ticked: Claude finds them).
  const [sheets, setSheets] = useState<Sheet[]>([])
  const [chosenSheets, setChosenSheets] = useState<string[]>([])
  useEffect(() => {
    setSheets([])
    setChosenSheets([])
    if (!workbook) return
    let current = true
    api.sheets(workbook).then((r) => { if (current) setSheets(r.sheets) }).catch(() => {})
    return () => { current = false }
  }, [workbook, listing.folder])
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

  useEffect(() => {
    if (selection) setDocuments(selection.documents)
  }, [selection])

  if (!listing.folder) return <aside className="job"><p className="muted">Open the workbook to fill to start.</p></aside>

  // Ticks or unticks every document shown (all of them, or those matching the filter).
  const words = filter.toLowerCase().split(/\s+/).filter(Boolean)
  const shown = listing.documents.filter((d) => words.every((w) => d.toLowerCase().includes(w)))
  const selectAll = (on: boolean) =>
    setDocuments((current) => (on ? [...current, ...shown.filter((d) => !current.includes(d))] : current.filter((d) => !shown.includes(d))))

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

      {sheets.length > 1 && (
        <fieldset className="sheets-box">
          <legend>Sheets to fill <span className="muted">(optional)</span></legend>
          <div className="sheets">
            {sheets.map((s) => (
              <label key={s.name} className="check" title={`${s.rows} rows × ${s.cols} columns`}>
                <input type="checkbox" checked={chosenSheets.includes(s.name)}
                  onChange={() => setChosenSheets((c) => (c.includes(s.name) ? c.filter((n) => n !== s.name) : [...c, s.name]))} />
                <span>{s.name} <small className="muted">{s.rows} × {s.cols}</small></span>
              </label>
            ))}
          </div>
          <p className="hint muted">{chosenSheets.length
            ? 'Only these sheets can be changed; the others are read only if a value depends on them.'
            : 'None ticked: Claude finds the sheet(s) to fill.'}</p>
        </fieldset>
      )}

      <fieldset className="documents-box">
        <legend>Documents to use ({documents.length} of {listing.documents.length})</legend>
        {listing.documents.length === 0 && <p className="muted">No PDF or image in this folder yet.</p>}
        {listing.documents.length > 1 && (
          <div className="documents-tools">
            {listing.documents.length > 6 && (
              <input type="search" placeholder="Filter documents…" value={filter} aria-label="Filter documents"
                onChange={(e) => setFilter(e.target.value)} />
            )}
            <button type="button" className="link" onClick={() => selectAll(true)}>All{filter ? ' shown' : ''}</button>
            <button type="button" className="link" onClick={() => selectAll(false)}>None{filter ? ' shown' : ''}</button>
          </div>
        )}
        <div className="documents">
          {shown.length === 0 && filter && <p className="muted">No document matches “{filter}”.</p>}
          {shown.map((d) => (
            <label key={d} className="check" title={d}>
              <input type="checkbox" checked={documents.includes(d)} onChange={() => toggle(d)} /> <DocumentName path={d} />
            </label>
          ))}
        </div>
      </fieldset>
      <div className="add-documents">
        <button onClick={onAddDocumentFolder} disabled={busy} title="Use the PDFs and images of another folder">Documents folder…</button>
        <button onClick={onAddDocuments} disabled={busy}>Add files…</button>
      </div>

      <label htmlFor="notes">Instructions <span className="muted">(optional)</span></label>
      <textarea id="notes" rows={4} placeholder="e.g. amounts excluding VAT, one row per line item, dates as dd/mm/yyyy"
        value={notes} onChange={(e) => setNotes(e.target.value)} />

      <p className="copy-hint" role="note">
        <b>Keep a copy of {workbook || 'the workbook'}</b> before filling it: the agent writes into this file
        (each change after your approval).
      </p>
      <button className="primary wide" disabled={busy || !workbook || documents.length === 0}
        onClick={() => onFill(workbook, documents, notes, sheets.filter((s) => chosenSheets.includes(s.name)).map((s) => s.name))}>
        Fill workbook
      </button>
    </aside>
  )
}
