// The job's activity: Claude's messages, what it is doing, and the changes it made or proposed.

import { useEffect, useRef } from 'react'
import { useLang } from '../i18n'
import type { Item } from '../types'
import { Change } from './Change'
import { ClaudeMessage } from './ClaudeMessage'

type Props = { items: Item[]; busy: boolean; activity: string; onOpen: (name: string) => void }

export function Activity({ items, busy, activity, onOpen }: Props) {
  const { lang, t } = useLang()
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
        <h2>{t('Fill a workbook from your documents')}</h2>
        {lang === 'fr' ? (
          <ol>
            <li>Ouvrez le classeur à remplir. Son dossier est l’endroit où l’agent travaille.</li>
            <li>Cochez les documents à utiliser dans ce dossier. S’ils sont ailleurs (en lecture seule) : <b>Changer de dossier…</b> pour les prendre dans un autre dossier, ou <b>Ajouter un dossier…</b> / <b>Ajouter des fichiers…</b> pour les ajouter.</li>
            <li><b>Travaillez sur une copie</b> (case cochée par défaut) : l’original n’est pas modifié.</li>
            <li>Appuyez sur <b>Remplir le classeur</b>. Vous approuvez chaque modification avant son enregistrement.</li>
          </ol>
        ) : (
        <ol>
          <li>Open the workbook to fill. Its folder is where the agent works.</li>
          <li>Tick the documents to use from that folder. If they are elsewhere (read only): <b>Change folder…</b> to take them from another folder, or <b>Add folder…</b> / <b>Add files…</b> to add them.</li>
          <li><b>Keep a copy of the workbook</b>: the agent writes into it.</li>
          <li>Press <b>Fill workbook</b>. You approve every change before it is saved.</li>
        </ol>
        )}
      </div>
    )
  }
  return (
    <div className="activity" aria-live="polite">
      {visible.map((item, i) => {
        switch (item.kind) {
          case 'claude':
            return <ClaudeMessage key={i} text={item.text} />
          case 'you':
            return <div key={i} className="you">{item.text}</div>
          case 'step':
            return (
              <div key={i} className="step">
                <span className="step-dot" aria-hidden /> {t(item.label)}
                {item.detail && <span className="step-detail"> {t(item.detail)}</span>}
                {item.failed && <div className="step-failed">{t('Did not work:')} {item.failed}</div>}
              </div>
            )
          case 'note':
            if (item.tone === 'error') return <div key={i} className="error-card" role="alert"><b>{t('Something went wrong.')}</b> {item.text}</div>
            return <div key={i} className={`note note-${item.tone}`}>{item.tone === 'success' ? '✔ ' : item.tone === 'failure' ? '✘ ' : ''}{item.text}</div>
          case 'saved':
            return (
              <div key={i} className="saved">
                <div>
                  <b>{item.name}</b> {t('is updated.')}
                  <small title={item.path}>{item.path}</small>
                  <small>{t('The previous version is kept in')} {item.backups}</small>
                </div>
                <button className="primary" onClick={() => onOpen(item.name)}>{t('Open in Excel')}</button>
              </div>
            )
          case 'change':
            return <Change key={i} item={item} />
        }
      })}
      {busy && <div className="working" role="status"><span className="spinner" aria-hidden /> {t(activity || 'Working…')}</div>}
      <div ref={end} />
    </div>
  )
}
