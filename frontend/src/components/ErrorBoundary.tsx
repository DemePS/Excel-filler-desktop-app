// If the window's code fails while showing something, say so (instead of a blank window) and
// send the error to the app's log file.

import { Component, type ReactNode } from 'react'
import { reportError } from '../api'
import { initialLang, translate } from '../i18n'

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    reportError(error.message, `${error.stack ?? ''}\n${info.componentStack ?? ''}`)
  }

  render() {
    if (!this.state.error) return this.props.children
    const t = (text: string) => translate(text, initialLang())  // outside the language provider: the saved choice
    return (
      <div className="crash" role="alert">
        <h2>{t('The window could not show the agent\'s progress.')}</h2>
        <p>{t('The job may still be running. Reloading the window shows its current state; the error was written to the log file.')}</p>
        <pre>{this.state.error.message}</pre>
        <button className="primary" onClick={() => window.location.reload()}>{t('Reload the window')}</button>
      </div>
    )
  }
}
