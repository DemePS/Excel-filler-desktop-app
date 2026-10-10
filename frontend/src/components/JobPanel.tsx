// The job: which workbook, which documents, and any instructions.

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useT } from '../i18n'
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
  const t = useT()
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

  if (!listing.folder) return <aside className="job"><p className="muted">{t('Open the workbook to fill to start.')}</p></aside>

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
        <label htmlFor="workbook" className="section-title">{t('Workbook')}</label>
        {listing.workbooks.length ? (
          <select id="workbook" value={workbook} onChange={(e) => setWorkbook(e.target.value)}>
            <option value="" disabled>{t('Choose a workbook…')}</option>
            {listing.workbooks.map((w) => <option key={w}>{w}</option>)}
          </select>
        ) : (
          <p className="muted">{t('No .xlsx or .xlsm file in this folder.')}</p>
        )}
        {sheets.length > 1 && (
          <details className="fold">
            <summary>{t('Sheets:')} <span className={chosen.length ? '' : 'muted'}>{chosen.length ? chosen.join(', ') : t('The assistant decides')}</span></summary>
            <div className="sheets">
              {sheets.map((s) => (
                <label key={s.name} className="check" title={t('{rows} rows × {cols} columns', { rows: s.rows, cols: s.cols })}>
                  <input type="checkbox" checked={chosenSheets.includes(s.name)}
                    onChange={() => setChosenSheets((c) => (c.includes(s.name) ? c.filter((n) => n !== s.name) : [...c, s.name]))} />
                  <span>{s.name} <small className="muted">{s.rows} × {s.cols}</small></span>
                </label>
              ))}
            </div>
            <p className="hint muted">{t('Ticked sheets are the only ones that can be changed.')}</p>
          </details>
        )}
      </section>

      <section className="job-section documents-box">
        <div className="section-head">
          <span className="section-title">{t('Documents')} <span className="count">{documents.length}/{listing.documents.length}</span></span>
          {listing.documents.length > 1 && (
            <span className="head-actions">
              <button type="button" className="link" onClick={() => selectAll(true)}>{t('All')}</button>
              <button type="button" className="link" onClick={() => selectAll(false)}>{t('None')}</button>
            </span>
          )}
        </div>
        <div className="documents-from" title={listing.documents_folder ?? listing.folder}>
          {t('From')} {listing.documents_folder ? <b>{listing.documents_folder.split(/[\\/]/).filter(Boolean).pop()}</b> : t('the workbook’s folder')}
          <button type="button" className="link" onClick={onChangeDocumentFolder} disabled={busy}
            title={t('Take the documents from another folder instead: pick any document in it')}>{t('Change folder…')}</button>
          {listing.documents_folder && (
            <button type="button" className="link" onClick={onResetDocumentFolder} disabled={busy}>{t('Use the workbook’s folder')}</button>
          )}
        </div>
        {listing.documents.length > 6 && (
          <input type="search" className="filter" placeholder={t('Filter…')} value={filter} aria-label={t('Filter documents')}
            onChange={(e) => setFilter(e.target.value)} />
        )}
        {listing.documents.length === 0 && <p className="muted">{t('No PDF or image in this folder yet.')}</p>}
        <div className="documents">
          {shown.length === 0 && filter && <p className="muted">{t('No document matches')} “{filter}”.</p>}
          {shown.map((d) => (
            <label key={d} className="check" title={d}>
              <input type="checkbox" checked={documents.includes(d)} onChange={() => toggle(d)} /> <DocumentName path={d} />
            </label>
          ))}
        </div>
        <div className="add-links">
          <button type="button" className="link" onClick={onAddDocuments} disabled={busy}>{t('Add files…')}</button>
          <button type="button" className="link" onClick={onAddDocumentFolder} disabled={busy}
            title={t('Add the PDFs and images of another folder: pick any document in it')}>{t('Add folder…')}</button>
        </div>
      </section>

      <details className="fold job-section">
        <summary>{t('Instructions')} <span className="muted">{notes.trim() ? '' : t('(optional)')}</span></summary>
        <textarea id="notes" rows={3} aria-label={t('Instructions')} placeholder={t('e.g. amounts excluding VAT, one row per line item')}
          value={notes} onChange={(e) => setNotes(e.target.value)} />
      </details>

      <div className="fill">
        <label className={`auto-switch${onCopy ? ' on' : ''}`} title={t('The workbook is copied next to the original (for example costs (copy).xlsx) and the copy is filled. The original is not changed.')}>
          <input type="checkbox" checked={onCopy} disabled={busy} onChange={(e) => setOnCopy(e.target.checked)} />
          <span>{t('Work on a copy')} <small>{onCopy ? t('the original is not changed') : t('the agent writes into the workbook itself')}</small></span>
        </label>
        <label className={`auto-switch${auto ? ' on' : ''}`} title={t('Changes are applied without asking you; questions are not asked (missing values are left empty and listed)')}>
          <input type="checkbox" checked={auto} disabled={busy} onChange={(e) => onAuto(e.target.checked)} />
          <span>{t('Auto mode')} <small>{auto ? t('changes are saved without asking') : t('you approve each change')}</small></span>
        </label>
        <button className="primary wide" disabled={busy || !workbook || documents.length === 0}
          onClick={() => onFill(workbook, documents, notes, chosen, onCopy)}>
          {t('Fill workbook')}
        </button>
        {!onCopy && <p className="copy-hint" role="note">⚠ {t('Keep a copy of {name} first: the agent writes into it.', { name: workbook || t('the workbook') })}</p>}
      </div>
    </aside>
  )
}
