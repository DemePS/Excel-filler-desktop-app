// The Help button: a question about ComptaIA or about what it did. With a workbook open it goes to the agent of the
// job (same conversation, the answer appears in the activity feed); before that, a short answer from the guide.

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useLang, useT } from '../i18n'
import { Markdown } from './Markdown'

type Turn = { role: 'user' | 'assistant'; text: string }

export function HelpDialog({ onClose }: { onClose: () => void }) {
  const t = useT()
  const { lang } = useLang()
  const [turns, setTurns] = useState<Turn[]>([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => input.current?.focus(), [])
  useEffect(() => end.current?.scrollIntoView({ block: 'end' }), [turns, busy])

  const send = async () => {
    const text = question.trim()
    if (!text || busy) return
    setError(null)
    setBusy(true)
    setQuestion('')
    const history = turns
    setTurns([...history, { role: 'user', text }])
    try {
      const result = await api.help(text, history, lang)
      if (result.started) { onClose(); return }  // the agent of the job answers in the activity feed
      setTurns((all) => [...all, { role: 'assistant', text: result.answer ?? '…' }])
    } catch (e) {
      setError((e as Error).message)
      setQuestion(text)
    } finally {
      setBusy(false)
      input.current?.focus()
    }
  }

  return (
    <div className="backdrop">
      <div className="dialog help" role="dialog" aria-modal="true" aria-labelledby="help-title">
        <h2 id="help-title">{t('Help')}</h2>
        <p className="hint muted">{t('Ask how to use ComptaIA, or why it filled a value. With a workbook open, the agent that did the work answers in the activity feed.')}</p>
        <div className="help-log">
          {turns.length === 0 && <p className="muted">{t('For example: how do I fill only one sheet? What does “Work on a copy” do?')}</p>}
          {turns.map((turn, i) => turn.role === 'user'
            ? <p key={i} className="help-you">{turn.text}</p>
            : <div key={i} className="help-answer"><Markdown text={turn.text} /></div>)}
          {busy && <p className="muted" role="status">{t('ComptaIA is thinking…')}</p>}
          <div ref={end} />
        </div>
        {error && <div className="banner error" role="alert">{error}</div>}
        <form className="help-form" onSubmit={(e) => { e.preventDefault(); send() }}>
          <textarea ref={input} rows={2} value={question} maxLength={1000} placeholder={t('Your question…')}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
          <div className="actions">
            <button type="button" onClick={onClose}>{t('Close')}</button>
            <button type="submit" className="primary" disabled={busy || !question.trim()}>{t('Send')}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
