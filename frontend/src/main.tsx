import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { reportError } from './api'
import { ErrorBoundary } from './components/ErrorBoundary'

// Errors outside rendering (event handlers, promises) go to the log file too.
window.addEventListener('error', (e) => reportError(e.message, (e.error as Error | undefined)?.stack))
window.addEventListener('unhandledrejection', (e) => reportError(String((e.reason as Error)?.message ?? e.reason), (e.reason as Error)?.stack))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
