// The job: which workbook, which documents, and any instructions.

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Listing, Sheet } from '../types'

type Props = {
  listing: Listing
  busy: boolean
  onFill: (workbook: string, documents: string[], notes: string, sheets: string[], copy: boolean) => void
  onAddDocuments: () => void
  auto: boolean
  onAuto: (on: boolean) => void
  onAddDocumentFolder: () => void
  onChangeDocumentFolder: () => void
  onResetDocumentFolder: () => void
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

export function JobPanel({ listing, busy, onFill, onAddDocuments, onAddDocumentFolder, onChangeDocumentFolder, onResetDocumentFolder, selection, auto, onAuto }: Props) {
  const [workbook, setWorkbook] = useState('')
  const [documents, setDocuments] = useState<string[]>([])
  const [notes, setNotes] = useState('')
  // Fill a copy next to the workbook, so that the original is never changed (ticked unless the person unticks it).
  const [onCopy, setOnCopy] = useState(true)
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

  const chosen = sheets.filter((s) => chosenSheets.includes(s.name)).map((s) => s.name)

  return (
    <aside className="job">
      <section className="job-section">
        <label htmlFor="workbook" className="section-title">Workbook</label>
        {listing.workbooks.length ? (
          <select id="workbook" value={workbook} onChange={(e) => setWorkbook(e.target.value)}>
            <option value="" disabled>Choose a workbook…</option>
            {listing.workbooks.map((w) => <option key={w}>{w}</option>)}
          </select>
        ) : (
          <p className="muted">No .xlsx or .xlsm file in this folder.</p>
        )}
        {sheets.length > 1 && (
          <details className="fold">
            <summary>Sheets: <span className={chosen.length ? '' : 'muted'}>{chosen.length ? chosen.join(', ') : 'Claude decides'}</span></summary>
            <div className="sheets">
              {sheets.map((s) => (
                <label key={s.name} className="check" title={`${s.rows} rows × ${s.cols} columns`}>
                  <input type="checkbox" checked={chosenSheets.includes(s.name)}
                    onChange={() => setChosenSheets((c) => (c.includes(s.name) ? c.filter((n) => n !== s.name) : [...c, s.name]))} />
                  <span>{s.name} <small className="muted">{s.rows} × {s.cols}</small></span>
                </label>
              ))}
            </div>
            <p className="hint muted">Ticked sheets are the only ones that can be changed.</p>
          </details>
        )}
      </section>

      <section className="job-section documents-box">
        <div className="section-head">
          <span className="section-title">Documents <span className="count">{documents.length}/{listing.documents.length}</span></span>
          {listing.documents.length > 1 && (
            <span className="head-actions">
              <button type="button" className="link" onClick={() => selectAll(true)}>All</button>
              <button type="button" className="link" onClick={() => selectAll(false)}>None</button>
            </span>
          )}
        </div>
        <div className="documents-from" title={listing.documents_folder ?? listing.folder}>
          From {listing.documents_folder ? <b>{listing.documents_folder.split(/[\\/]/).filter(Boolean).pop()}</b> : 'the workbook’s folder'}
          <button type="button" className="link" onClick={onChangeDocumentFolder} disabled={busy}
            title="Take the documents from another folder instead: pick any document in it">Change folder…</button>
          {listing.documents_folder && (
            <button type="button" className="link" onClick={onResetDocumentFolder} disabled={busy}>Use the workbook’s folder</button>
          )}
        </div>
        {listing.documents.length > 6 && (
          <input type="search" className="filter" placeholder="Filter…" value={filter} aria-label="Filter documents"
            onChange={(e) => setFilter(e.target.value)} />
        )}
        {listing.documents.length === 0 && <p className="muted">No PDF or image in this folder yet.</p>}
        <div className="documents">
          {shown.length === 0 && filter && <p className="muted">No document matches “{filter}”.</p>}
          {shown.map((d) => (
            <label key={d} className="check" title={d}>
              <input type="checkbox" checked={documents.includes(d)} onChange={() => toggle(d)} /> <DocumentName path={d} />
            </label>
          ))}
        </div>
        <div className="add-links">
          <button type="button" className="link" onClick={onAddDocuments} disabled={busy}>Add files…</button>
          <button type="button" className="link" onClick={onAddDocumentFolder} disabled={busy}
            title="Add the PDFs and images of another folder: pick any document in it">Add folder…</button>
        </div>
      </section>

      <details className="fold job-section">
        <summary>Instructions <span className="muted">{notes.trim() ? '' : '(optional)'}</span></summary>
        <textarea id="notes" rows={3} aria-label="Instructions" placeholder="e.g. amounts excluding VAT, one row per line item"
          value={notes} onChange={(e) => setNotes(e.target.value)} />
      </details>

      <div className="fill">
        <label className={`auto-switch${onCopy ? ' on' : ''}`} title="The workbook is copied next to the original (for example costs (copy).xlsx) and the copy is filled. The original is not changed.">
          <input type="checkbox" checked={onCopy} disabled={busy} onChange={(e) => setOnCopy(e.target.checked)} />
          <span>Work on a copy <small>{onCopy ? 'the original is not changed' : 'the agent writes into the workbook itself'}</small></span>
        </label>
        <label className={`auto-switch${auto ? ' on' : ''}`} title="Changes are applied without asking you; questions are not asked (missing values are left empty and listed)">
          <input type="checkbox" checked={auto} disabled={busy} onChange={(e) => onAuto(e.target.checked)} />
          <span>Auto mode <small>{auto ? 'changes are saved without asking' : 'you approve each change'}</small></span>
        </label>
        <button className="primary wide" disabled={busy || !workbook || documents.length === 0}
          onClick={() => onFill(workbook, documents, notes, chosen, onCopy)}>
          Fill workbook
        </button>
        {!onCopy && <p className="copy-hint" role="note">⚠ Keep a copy of {workbook || 'the workbook'} first: the agent writes into it.</p>}
      </div>
    </aside>
  )
}
