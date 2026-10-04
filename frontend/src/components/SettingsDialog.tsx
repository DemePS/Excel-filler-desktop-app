// The Anthropic API key and model: tested with one tiny call, then saved on this PC.

import { useEffect, useRef, useState } from 'react'
import { api, hasNativeWindow, KEYS_URL, openExternal } from '../api'
import type { SettingsInfo } from '../types'

type Props = {
  info: SettingsInfo
  firstRun: boolean // nothing is set up yet: the dialog cannot be skipped
  onClose: () => void
  onChanged: (info: SettingsInfo) => void
}

export function SettingsDialog({ info, firstRun, onClose, onChanged }: Props) {
  const [key, setKey] = useState('')
  const [model, setModel] = useState(info.model)
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
      const result = await api.saveSettings(key, model)
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
          <h2 id="settings-title">{firstRun ? 'Add your Anthropic API key' : 'Settings'}</h2>
          <p className="hint">
            Excel filler uses Claude through your own Anthropic account; Anthropic bills you directly for what you use.{' '}
            {hasNativeWindow()
              ? <button type="button" className="link" onClick={() => openExternal(KEYS_URL)}>Get a key</button>
              : <>Get a key at <code>{KEYS_URL}</code></>}
          </p>
          {hasKey && <p className="hint">A key ending in <b>{info.key_hint}</b> is saved. Paste a new one to replace it.</p>}
          {info.source === 'foundry' && <p className="hint">Currently using the Azure Foundry setup of this PC. A key saved here is used instead.</p>}
          <label htmlFor="api-key">API key</label>
          <div className="key-row">
            <input id="api-key" ref={input} type={show ? 'text' : 'password'} value={key} onChange={(e) => setKey(e.target.value)}
              placeholder="sk-ant-…" autoComplete="new-password" spellCheck={false} autoCapitalize="off" />
            <button type="button" onClick={() => setShow(!show)} aria-pressed={show}>{show ? 'Hide' : 'Show'}</button>
          </div>
          <label htmlFor="model">Model</label>
          <select id="model" value={model} onChange={(e) => setModel(e.target.value)}>
            {info.models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
          <p className="hint">
            {info.storage === 'credential-manager'
              ? 'The key is stored for your Windows account (Credential Manager) and sent only to Anthropic.'
              : <b>This PC has no secure storage for keys: the key will not be remembered after you close the app.</b>}
          </p>
          {error && <div className="banner error" role="alert">{error}</div>}
          <div className="actions">
            {hasKey && <button type="button" className="danger" disabled={busy} onClick={remove}>Remove key</button>}
            {!firstRun && <button type="button" onClick={close} disabled={busy}>Close</button>}
            <button type="submit" className="primary" disabled={busy || !key.trim()}>{busy ? 'Testing…' : 'Test and save'}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
