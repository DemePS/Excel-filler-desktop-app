// Before the session starts: signing in, then checking that this person is an authorized Excel
// filler user (through the organization's gateway). Also shown if access is refused later.

import type { Access } from '../types'

const TITLES: Record<string, string> = {
  denied: 'You are not allowed to use Excel filler',
  signin_failed: 'Sign-in did not complete',
  unreachable: 'The Excel filler service cannot be reached',
}

export function AccessScreen({ access, checking, onRetry }: { access: Access | null; checking: boolean; onRetry: () => void }) {
  return (
    <div className="access-screen">
      <div className="access-card" role={checking ? 'status' : 'alert'}>
        <div className="brand"><span className="logo" aria-hidden /> Excel filler</div>
        {checking ? (
          <>
            <h1><span className="spinner" aria-hidden /> Signing in…</h1>
            <p>Checking your work account and your access to Excel filler.</p>
            <p className="muted">If a Microsoft sign-in page opens in your browser, finish signing in there.</p>
          </>
        ) : (
          <>
            <h1>{TITLES[access?.state ?? ''] ?? 'Excel filler cannot start'}</h1>
            {access?.user && <p>Signed in as <b>{access.user}</b>.</p>}
            {access?.message && <p>{access.message}</p>}
            {access?.state === 'denied' && (
              <p className="muted">Excel filler is available to members of the Excel filler users group. If IT has
                just added you, it can take up to an hour before your access is active.</p>
            )}
            <button className="primary" onClick={onRetry}>Try again</button>
          </>
        )}
      </div>
    </div>
  )
}
