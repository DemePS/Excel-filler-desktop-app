// One of Claude's messages, with a Copy button: the formatted message (tables, bold... kept when
// pasted into Word, Outlook or Excel) and its plain text (Markdown) for anything else.

import { useRef, useState } from 'react'
import { Markdown } from './Markdown'

async function copy(text: string, html: string): Promise<void> {
  try {
    if (navigator.clipboard && 'ClipboardItem' in window) {
      await navigator.clipboard.write([new ClipboardItem({
        'text/plain': new Blob([text], { type: 'text/plain' }),
        'text/html': new Blob([html], { type: 'text/html' }),
      })])
      return
    }
    await navigator.clipboard.writeText(text)
  } catch {
    // No clipboard API here (or refused): the older way, with a hidden text field.
    const field = document.createElement('textarea')
    field.value = text
    field.style.position = 'fixed'
    field.style.opacity = '0'
    document.body.appendChild(field)
    field.select()
    document.execCommand('copy')
    field.remove()
  }
}

export function ClaudeMessage({ text }: { text: string }) {
  const body = useRef<HTMLDivElement>(null)
  const [copied, setCopied] = useState(false)
  return (
    <div className="claude">
      <button type="button" className="copy" aria-label="Copy this message" title="Copy this message"
        onClick={async () => {
          await copy(text, body.current?.innerHTML ?? text)
          setCopied(true)
          window.setTimeout(() => setCopied(false), 1500)
        }}>
        {copied ? 'Copied ✓' : 'Copy'}
      </button>
      <div ref={body}><Markdown text={text} /></div>
    </div>
  )
}
