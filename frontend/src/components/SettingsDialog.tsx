// The DeepSeek API key: tested with one tiny call, then saved on this PC.

import { useEffect, useRef, useState } from 'react'
import { api, openExternal } from '../api'
import { useT } from '../i18n'
import type { SettingsInfo } from '../types'

type Props = {
  info: SettingsInfo
  firstRun: boolean // nothing is set up yet: the dialog cannot be skipped
  onClose: () => void
  onChanged: (info: SettingsInfo) => void
}

export function SettingsDialog({ info, firstRun, onClose, onChanged }: Props) {
  const t = useT()
  const [key, setKey] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => input.current?.focus(), [])

  // The key is only kept in this component while it is typed: cleared on submit and on close.
  const close = () => { setKey(''); onClose() }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await api.saveSettings(key)
      setKey('')
      onChanged(result)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    setError(null)
    try {
      onChanged(await api.removeKey())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const hasKey = info.source === 'saved'
  return (
    <div className="backdrop">
      <div className="dialog settings" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <form onSubmit={(e) => { e.preventDefault(); if (key.trim() && !busy) save() }} autoComplete="off">
          <h2 id="settings-title">{firstRun ? t('Add your API key') : t('Settings')}</h2>
          <p className="hint">
            {t('ComptaIA uses an AI model through your own DeepSeek account; DeepSeek bills you directly for what you use.')}
          </p>
          <p className="hint">
            <button type="button" onClick={() => openExternal(info.keys_url)}>{t('Get my API key')}</button>{' '}
            <span className="muted">{info.keys_url.replace('https://', '')}</span>
          </p>
          <p className="hint muted">{t('ComptaIA is not affiliated with DeepSeek or Microsoft.')}</p>
          {hasKey && <p className="hint">{t('A key ending in')} <b>{info.key_hint}</b> {t('is saved. Paste a new one to replace it.')}</p>}
          {info.source === 'foundry' && <p className="hint">{t('Currently using the Azure Foundry setup of this PC. A key saved here is used instead.')}</p>}
          <label htmlFor="api-key">{t('API key')}</label>
          <div className="key-row">
            <input id="api-key" ref={input} type={show ? 'text' : 'password'} value={key} onChange={(e) => setKey(e.target.value)}
              placeholder="sk-…" autoComplete="new-password" spellCheck={false} autoCapitalize="off" />
            <button type="button" onClick={() => setShow(!show)} aria-pressed={show}>{show ? t('Hide') : t('Show')}</button>
          </div>
          <p className="hint">
            {info.storage === 'credential-manager'
              ? t('The key is stored for your Windows account (Credential Manager) and sent only to DeepSeek.')
              : <b>{t('This PC has no secure storage for keys: the key will not be remembered after you close the app.')}</b>}
          </p>
          {error && <div className="banner error" role="alert">{error}</div>}
          <div className="actions">
            {hasKey && <button type="button" className="danger" disabled={busy} onClick={remove}>{t('Remove key')}</button>}
            {!firstRun && <button type="button" onClick={close} disabled={busy}>{t('Close')}</button>}
            <button type="submit" className="primary" disabled={busy || !key.trim()}>{busy ? t('Testing…') : t('Test and save')}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
