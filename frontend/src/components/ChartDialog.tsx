// The chart of accounts (plan comptable) ComptaIA looks accounts up in: shows the current file and
// replaces it with a PDF, text or CSV file chosen on this PC.

import { useEffect, useState } from 'react'
import { getChart, pickChart, updateChart, type ChartInfo } from '../api'
import { useLang, useT } from '../i18n'

export function ChartDialog({ onClose }: { onClose: () => void }) {
  const t = useT()
  const { lang } = useLang()
  const [info, setInfo] = useState<ChartInfo | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  useEffect(() => { getChart().then(setInfo).catch((e: Error) => setError(e.message)) }, [])

  const choose = async () => {
    setError(null)
    setDone(false)
    const path = await pickChart()
    if (!path) return
    setBusy(true)
    try {
      setInfo(await updateChart(path))
      setDone(true)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const modified = info?.modified ? new Date(info.modified * 1000).toLocaleDateString(lang === 'fr' ? 'fr-FR' : 'en-GB') : null
  return (
    <div className="backdrop">
      <div className="dialog settings" role="dialog" aria-modal="true" aria-labelledby="chart-title">
        <h2 id="chart-title">{t('Chart of accounts')}</h2>
        <p className="hint">
          {t('ComptaIA looks account numbers up in this file and never writes them from memory. Choose the new version (PDF or text): it replaces the current one.')}
        </p>
        <p>
          {info === null ? '…' : info.file
            ? <><b>{info.file}</b> {modified && <span className="muted">({t('updated')} {modified})</span>}</>
            : <span className="muted">{t('No chart of accounts yet.')}</span>}
        </p>
        {info && <p className="hint muted">{t('Folder:')} <code>{info.folder}</code></p>}
        {busy && <p className="hint" role="status">{t('Reading the file and preparing the search…')}</p>}
        {done && !busy && <p className="hint" role="status">{t('Chart of accounts updated.')}</p>}
        {error && <div className="banner error" role="alert">{error}</div>}
        <div className="actions">
          <button type="button" onClick={onClose} disabled={busy}>{t('Close')}</button>
          <button type="button" className="primary" onClick={choose} disabled={busy}>{t('Choose a file…')}</button>
        </div>
      </div>
    </div>
  )
}
